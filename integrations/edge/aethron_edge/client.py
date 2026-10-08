"""Strict observation consumer. Unknown transit cannot establish current evidence."""

import time

from .contracts import SceneEnvelope


class Observation:
    def __init__(self):
        self.scene = None
        self.received_ns = 0

    def accept(self, value, *, received_ns=None):
        self.disconnect()
        self.scene = SceneEnvelope.model_validate(value)
        self.received_ns = time.monotonic_ns() if received_ns is None else received_ns

    def disconnect(self):
        self.scene = None

    def view(self, *, now_ns=None):
        now_ns = time.monotonic_ns() if now_ns is None else now_ns
        if (
            self.scene is None
            or not 0 <= now_ns - self.received_ns <= self.scene.clock.valid_for_ms * 1_000_000
        ):
            self.disconnect()
            return {
                "label": "expired",
                "current_state": "UNKNOWN",
                "observed_state": "UNKNOWN",
                "sources": [],
                "uncertainty": [],
            }
        return {
            "label": "delayed_observation",
            "current_state": "UNKNOWN",
            "observed_state": self.scene.result.state,
            "sources": sorted({s for track in self.scene.result.tracks for s in track.sources}),
            "uncertainty": [track.covariance for track in self.scene.result.tracks],
        }


def bounded_lines(chunks, limit=65536):
    pending = bytearray()
    for chunk in chunks:
        # Callers request bounded transport chunks; reject unbounded custom input.
        if len(chunk) > limit:
            raise ValueError("event_limit")
        for part in chunk.splitlines(keepends=True):
            if len(pending) + len(part) > limit:
                raise ValueError("event_limit")
            pending.extend(part)
            if pending.endswith(b"\n"):
                yield bytes(pending).rstrip(b"\r\n").decode("utf-8")
                pending.clear()
    if pending:
        raise ValueError("incomplete_event")


def observe(url, token, profile, contract="warn", limit=None):
    import httpx

    value = Observation()
    with httpx.Client(
        base_url=url, headers={"Authorization": "Bearer " + token}, timeout=2
    ) as client:
        response = client.post(
            "/api/v1/sessions", json={"source_profile": profile, "contract": contract}
        )
        response.raise_for_status()
        handle = response.json()["session"]
        try:
            with client.stream("GET", f"/api/v1/sessions/{handle}/events") as stream:
                stream.raise_for_status()
                count = 0
                for line in bounded_lines(stream.iter_bytes(chunk_size=1024)):
                    if len(line) > 65536:
                        raise ValueError("event_limit")
                    if line.startswith("data: "):
                        from .config import strict_json

                        data = strict_json(line[6:].encode())
                        if data.get("kind") != "scene":
                            value.disconnect()
                            continue
                        value.accept(data)
                        yield value.view()
                        count += 1
                        if limit is not None and count >= limit:
                            return
        finally:
            value.disconnect()
            try:
                client.delete("/api/v1/sessions/" + handle)
            except httpx.HTTPError:
                pass
