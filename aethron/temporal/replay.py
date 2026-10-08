"""Explicit bounded synthetic/recorded replay, not a live-person logging interface."""

from ..schema import MAX_BYTES, parse, require
from .session import Session


class ReplayError(ValueError):
    """Fixed fail-safe action only; never carries the rejected payload."""

    def __init__(self, action):
        super().__init__("invalid_input")
        self.action = action


def replay(stream):
    session = Session()
    first, count, ids = None, 0, {}
    clock = 0
    try:
        while True:
            line = stream.readline(MAX_BYTES + 1)
            if not line:
                break
            require(len(line) <= MAX_BYTES)
            frame = parse(line)
            require(frame["version"] == 3 and frame["evidence"] in ("synthetic", "recorded"))
            count += 1
            require(count <= 300)
            at = frame["at_ms"]
            if first is None:
                first = at
            require(0 <= at - first < 30000)
            clock = at
            result = session.step(line, now_ms=at)
            require("invalid_input" not in result["reasons"])
            active = {t["id"] for t in result["tracks"]}
            # Retain only the currently active map, never a history of expired IDs.
            ids = {k: v for k, v in ids.items() if k in active}
            for t in result["tracks"]:
                if t["id"] not in ids:
                    ids[t["id"]] = "replay-" + str(count) + "-" + str(len(ids) + 1)
                t["id"] = ids[t["id"]]
            yield result
    except (ValueError, OSError):
        session.close()
        action = session.watchdog(now_ms=clock)["recommendation"]["action"]
        raise ReplayError(action) from None
    finally:
        session.close()
