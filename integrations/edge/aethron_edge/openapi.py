"""Deterministic OpenAPI export from strict runtime models (no CDN dependency)."""

from .contracts import (
    Capabilities,
    Error,
    HealthEvent,
    ReplayReport,
    SceneEnvelope,
    SessionHandle,
    SessionRequest,
)


def document():
    schemas = {}
    for model in (
        Capabilities,
        Error,
        HealthEvent,
        ReplayReport,
        SceneEnvelope,
        SessionHandle,
        SessionRequest,
    ):
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        schemas.update(schema.pop("$defs", {}))
        schemas[model.__name__] = schema

    def response(name):
        return {
            "description": name,
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/" + name}}},
        }

    def operation(name, status="200"):
        return {
            "security": [{"bearerAuth": []}],
            "responses": {
                status: response(name),
                **{str(code): response("Error") for code in (401, 403, 404, 409, 413, 422, 429)},
            },
        }

    paths = {
        "/healthz": {"get": {"responses": {"200": {"description": "Process liveness only"}}}},
        "/api/v1/capabilities": {"get": operation("Capabilities")},
        "/api/v1/replays": {"post": operation("ReplayReport")},
        "/api/v1/sessions": {"post": operation("SessionHandle", "201")},
        "/api/v1/sessions/{session}/snapshot": {"get": operation("SceneEnvelope")},
        "/api/v1/sessions/{session}/events": {"get": operation("SceneEnvelope")},
        "/api/v1/sessions/{session}": {
            "delete": {
                "security": [{"bearerAuth": []}],
                "responses": {
                    "204": {"description": "Viewer detached"},
                    "401": response("Error"),
                    "403": response("Error"),
                },
            }
        },
    }
    paths["/api/v1/replays"]["post"]["requestBody"] = {
        "required": True,
        "content": {
            "application/x-ndjson": {
                "schema": {"type": "string", "maxLength": 20971520},
                "description": "Unchanged raw v3 bytes; <=300 frames, span <30000ms; each <=65536 bytes, depth <=8. Duplicate keys/nonfinite values rejected.",
            }
        },
    }
    paths["/api/v1/sessions"]["post"]["requestBody"] = {
        "required": True,
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/SessionRequest"}}
        },
    }
    paths["/api/v1/sessions/{session}/events"]["get"]["responses"]["200"] = {
        "description": "Latest-only SSE scene/health/gap; no historical resumption",
        "content": {"text/event-stream": {"schema": {"type": "string"}}},
    }
    for path, item in paths.items():
        if "{session}" in path:
            item["parameters"] = [
                {
                    "name": "session",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
                }
            ]
    return {
        "openapi": "3.1.1",
        "info": {"title": "AETHRON edge", "version": "0.1.0"},
        "paths": paths,
        "components": {
            "schemas": schemas,
            "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}},
        },
    }
