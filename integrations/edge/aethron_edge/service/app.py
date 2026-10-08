"""Authenticated loopback service; data never enters an actuator interface."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.exceptions import HTTPException

from ..config import strict_json
from ..contracts import Capabilities, Error, SessionRequest
from ..openapi import document
from ..protocol import replay_bytes
from ..runtime.supervisor import ApplianceSupervisor
from .auth import Auth
from .events import stream
from .sessions import ServiceError, Sessions


def error(status, code):
    return JSONResponse(
        Error(api_version="1", error=code, retryable=False).model_dump(), status_code=status
    )


class Boundary:
    def __init__(self, app, auth, port):
        self.app = app
        self.auth = auth
        self.port = port

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = scope.get("headers", [])
        # Duplicate credential/Host headers are ambiguous, never last-value wins.
        names = [k.lower() for k, v in headers]
        h = {k.lower(): v for k, v in headers}
        denied = None
        if any(names.count(name) > 1 for name in (b"host", b"authorization", b"content-length")):
            denied = error(422, "invalid_request")
        allowed = {
            f"127.0.0.1:{self.port}".encode(),
            f"localhost:{self.port}".encode(),
            f"[::1]:{self.port}".encode(),
        }
        if h.get(b"host") not in allowed or b"origin" in h or scope.get("query_string"):
            denied = error(403, "forbidden")
        principal = self.auth.authenticate(h.get(b"authorization", b"").decode("latin1"))
        if scope["path"] != "/healthz" and principal is None:
            denied = error(401, "unauthorized")
        if denied:
            return await denied(scope, receive, send)
        scope.setdefault("state", {})["principal"] = principal

        async def bounded_send(message):
            await asyncio.wait_for(send(message), timeout=2)

        try:
            await self.app(scope, receive, bounded_send)
        except (TimeoutError, ConnectionError, asyncio.CancelledError):
            return


def create_app(config):
    auth = Auth(config.credentials)
    supervisor = ApplianceSupervisor()
    sessions = Sessions(supervisor)
    subscribers = 0
    replay_gate = asyncio.Semaphore(1)

    @asynccontextmanager
    async def lifespan(app):
        supervisor.boot(config)
        try:
            yield
        finally:
            supervisor.shutdown()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(Boundary, auth=auth, port=config.port)
    app.openapi = document

    @app.exception_handler(HTTPException)
    async def route_error(request, exc):
        return error(
            404 if exc.status_code == 404 else 422,
            "not_found" if exc.status_code == 404 else "invalid_request",
        )

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return error(exc.status, exc.error)

    @app.get("/healthz")
    async def health():
        return {"alive": True}

    @app.get("/api/v1/capabilities")
    async def capabilities(request: Request):
        if "observe" not in request.state.principal.scopes:
            return error(403, "forbidden")
        return Capabilities(
            api_version="1",
            core_version="0.2.0",
            edge_version="0.1.0",
            protocol=3,
            runtime_mode=config.runtime_mode,
            drivers=sorted({p.driver for p in config.profiles}),
            provider=",".join(
                sorted(
                    {
                        "recorded_geometry" if p.driver == "sensor-replay" else p.provider
                        for p in config.profiles
                        if p.driver != "replay"
                    }
                )
            )
            or "replay_virtual",
            qualification_refs=[],
        )

    async def body(request, limit):
        value = bytearray()
        async with asyncio.timeout(5):
            async for chunk in request.stream():
                if len(value) + len(chunk) > limit:
                    raise ServiceError(413, "invalid_request")
                value.extend(chunk)
        return bytes(value)

    @app.post("/api/v1/replays")
    async def replays(request: Request):
        if "observe" not in request.state.principal.scopes:
            return error(403, "forbidden")
        if replay_gate.locked():
            return error(429, "capacity")
        async with replay_gate:
            try:
                data = await body(request, 20 * 1024 * 1024)
                if any(len(line) > 65536 for line in data.splitlines(keepends=True)):
                    return error(413, "invalid_request")
                result = await asyncio.to_thread(replay_bytes, data)
                return JSONResponse(result.model_dump(by_alias=True))
            except (ValueError, TimeoutError):
                return error(422, "invalid_request")

    @app.post("/api/v1/sessions")
    async def attach(request: Request):
        try:
            values = SessionRequest.model_validate(strict_json(await body(request, 4096), 4096))
        except (ValueError, TimeoutError, RecursionError):
            return error(422, "invalid_request")
        handle = sessions.open_session(
            values.source_profile, values.contract, request.state.principal
        )
        return JSONResponse(handle.model_dump(), status_code=201)

    @app.get("/api/v1/sessions/{token}/snapshot")
    async def snapshot(token: str, request: Request):
        return JSONResponse(
            sessions.snapshot(token, request.state.principal).model_dump(by_alias=True)
        )

    @app.delete("/api/v1/sessions/{token}")
    async def detach(token: str, request: Request):
        sessions.close_session(token, request.state.principal)
        return Response(status_code=204)

    @app.get("/api/v1/sessions/{token}/events")
    async def events(token: str, request: Request):
        nonlocal subscribers
        sessions.get(token, request.state.principal)
        if subscribers >= 8:
            return error(429, "capacity")
        subscribers += 1

        async def limited():
            nonlocal subscribers
            try:
                async for chunk in stream(sessions, token, request.state.principal):
                    yield chunk
            except ServiceError:
                return
            finally:
                subscribers -= 1

        return StreamingResponse(
            limited(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return app


def serve(config):
    import uvicorn

    uvicorn.run(
        create_app(config),
        host=config.host,
        port=config.port,
        access_log=False,
        log_level="critical",
        limit_concurrency=16,
        timeout_keep_alive=2,
        timeout_graceful_shutdown=5,
        proxy_headers=False,
    )
