import secrets
import threading
import time

from ..contracts import Clock, SceneEnvelope, SessionHandle, V3Snapshot


class ServiceError(ValueError):
    def __init__(self, status, error):
        self.status = status
        self.error = error


class Sessions:
    def __init__(self, supervisor):
        self.supervisor = supervisor
        self.handles = {}
        self.lock = threading.RLock()

    def open_session(self, profile, contract, principal):
        with self.lock:
            if "session:manage" not in principal.scopes:
                raise ServiceError(403, "forbidden")
            pipeline = self.supervisor.pipelines.get(profile)
            if pipeline is None or pipeline.profile.contract != contract:
                raise ServiceError(409, "source_unavailable")
            if len(self.handles) >= 4:
                raise ServiceError(429, "capacity")
            token = secrets.token_hex(16)
            self.handles[token] = {"owner": principal.name, "profile": profile, "sequence": 0}
            return SessionHandle(session=token, source_profile=profile)

    def get(self, token, principal):
        row = self.handles.get(token)
        if row is None:
            raise ServiceError(404, "not_found")
        if row["owner"] != principal.name or "observe" not in principal.scopes:
            raise ServiceError(403, "forbidden")
        return row

    def snapshot(self, token, principal):
        with self.lock:
            row = self.get(token, principal)
            result = self.supervisor.snapshot(row["profile"])
            row["sequence"] += 1
            emitted_ms = time.monotonic_ns() // 1_000_000
            lease = (
                min(
                    [100]
                    + [
                        max(0, t["expires_at_ms"] - emitted_ms)
                        for t in result["tracks"]
                        if t["status"] == "PRESENT"
                    ]
                )
                if result["state"] == "PRESENT"
                else 0
            )
            return SceneEnvelope(
                api_version="1",
                kind="scene",
                sequence=row["sequence"],
                session=token,
                clock=Clock(domain="edge_monotonic", emitted_ms=emitted_ms, valid_for_ms=lease),
                result=V3Snapshot.model_validate(result),
            )

    def close_session(self, token, principal):
        with self.lock:
            if "session:manage" not in principal.scopes:
                raise ServiceError(403, "forbidden")
            if token in self.handles:
                self.get(token, principal)
                del self.handles[token]
