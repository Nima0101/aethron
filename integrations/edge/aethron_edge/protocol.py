"""Raw bytes cross the frozen core boundary without coercion."""

import io

from aethron.temporal.replay import replay

from .contracts import ReplayReport


def replay_bytes(data: bytes) -> ReplayReport:
    if not isinstance(data, bytes) or len(data) > 20 * 1024 * 1024:
        raise ValueError("invalid_request")
    results = list(replay(io.BytesIO(data)))
    if not results:
        raise ValueError("invalid_request")
    return ReplayReport.model_validate(
        {
            "api_version": "1",
            "runtime_mode": "replay",
            "frame_count": len(results),
            "results": results,
        }
    )
