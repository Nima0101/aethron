"""Time-bounded parser/adversarial fuzz with reproducible seed and explicit count."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import random
import time

from rescuesense import evaluate
from rescuesense.demo import scenarios


def run(seconds=60):
    rng = random.Random(54777)
    seeds = [data for _, data in scenarios()] + [b"[]", b"null", b"\xff", b"[" * 1000, b"0" * 65536]
    start = time.monotonic()
    count = accepted = 0
    while time.monotonic() - start < seconds:
        data = bytearray(rng.choice(seeds))
        mode = rng.randrange(4)
        if mode == 0:
            for _ in range(rng.randrange(1, 12)):
                if data:
                    data[rng.randrange(len(data))] = rng.randrange(256)
        elif mode == 1:
            data = data[: rng.randrange(len(data) + 1)]
        elif mode == 2:
            data.extend(rng.randbytes(rng.randrange(100)))
        try:
            result = evaluate(bytes(data))
            accepted += 1
            assert result["recommendation"]["action"] in (
                "WARN",
                "STOP",
                "HOVER",
                "LAND",
                "RETREAT",
            )
            assert "SAFE" not in json.dumps(result)
            assert len(result["claims"]) <= 16
        except ValueError as exc:
            assert str(exc) == "invalid_input"
        count += 1
    return {
        "seconds": time.monotonic() - start,
        "cases": count,
        "accepted": accepted,
        "seed": 54777,
        "unexpected_exceptions": 0,
    }


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
