"""Raw bytes cross the frozen core boundary without coercion."""

import io
from typing import BinaryIO

from aethron.temporal.replay import replay

from .contracts import ReplayReport


def replay_bytes(data: bytes) -> ReplayReport:
    if not isinstance(data, bytes) or len(data) > 20 * 1024 * 1024:
        raise ValueError("invalid_request")
    return replay_stream(io.BytesIO(data))


def replay_stream(stream: BinaryIO) -> ReplayReport:
    """Consume bounded lines; return a report only after the complete replay succeeds.

    The core reads at most 65537 bytes per line and rejects frame 301, so even
    a growing file cannot consume 20 MiB. The caller owns/closes the stream.
    """
    results = list(replay(stream))
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
