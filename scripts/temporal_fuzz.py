"""Deterministic mutation/state fuzz for at least60 seconds; fixed failures are not discarded."""

import hashlib
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aethron.temporal import Session  # noqa: E402
from aethron.temporal.fixtures import detection, encode, frame  # noqa: E402
from aethron.temporal.pixels import decode_pgm  # noqa: E402


def run():
    source_hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT / "aethron").rglob("*.py")
    }
    rng = random.Random(981640)
    s = Session()
    count = 0
    started = time.monotonic()
    while time.monotonic() - started < 60:
        now = count * 10
        seed = bytearray(encode(frame(now, [detection(rng.random() * 0.8)])))
        for _ in range(rng.randrange(1, 10)):
            p = rng.randrange(len(seed))
            seed[p] = rng.randrange(256)
        result = s.step(bytes(seed), now_ms=now)
        assert len(result["tracks"]) <= 32
        assert result["state"] in ("UNKNOWN", "PRESENT")
        assert result["recommendation"]["action"] in ("STOP", "WARN", "HOVER", "LAND", "RETREAT")
        if count % 7 == 0:
            valid = frame(now + 1, [detection()])
            valid["sensors"][0]["quality"] = rng.choice(["valid", "dark", "dropped", "multipath"])
            result = s.step(encode(valid), now_ms=now + 1)
            s.watchdog(now_ms=now + 700)
            assert not s._tracks
        try:
            decode_pgm(bytes(seed))
        except ValueError:
            pass
        count += 1
    s.close()
    assert source_hashes == {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT / "aethron").rglob("*.py")
    }, "source changed during fuzz"
    report = {
        "seed": 981640,
        "cases": count,
        "seconds": round(time.monotonic() - started, 3),
        "unexpected_exceptions": 0,
        "source_sha256": source_hashes,
    }
    out = ROOT / "build/v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / "fuzz.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    run()
