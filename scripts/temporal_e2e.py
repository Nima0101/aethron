"""Actual CLI replay, deterministic outputs, sensor-loss and corrupt-stream exit behavior."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run():
    args = [sys.executable, "-m", "aethron", "replay", "examples/temporal-blackout.jsonl"]
    a = subprocess.run(args, cwd=ROOT, capture_output=True, check=True)
    b = subprocess.run(args, cwd=ROOT, capture_output=True, check=True)
    assert a.stdout == b.stdout
    rows = [json.loads(line) for line in a.stdout.splitlines()]
    assert len(rows) == 24
    assert len({r["tracks"][0]["id"] for r in rows}) == 1
    assert rows[-1]["tracks"][0]["sources"] == ["depth", "lwir", "radar"]
    assert rows[-1]["recommendation"]["action"] == "STOP"
    with tempfile.TemporaryDirectory(prefix="aethron-replay-") as directory:
        path = Path(directory) / "invalid.jsonl"
        path.write_bytes(
            (ROOT / "examples/temporal-blackout.jsonl").read_bytes() + b'{"secret":"DO_NOT_ECHO"}\n'
        )
        failure = subprocess.run([*args[:4], str(path)], cwd=ROOT, capture_output=True, check=False)
        assert failure.returncode == 2
        assert b"DO_NOT_ECHO" not in failure.stderr + failure.stdout
        assert json.loads(failure.stderr)["state"] == "UNKNOWN"
        assert json.loads(failure.stderr)["action"] == "STOP"
    print(
        "PASS: actual temporal CLI, deterministic replay, blackout provenance, corrupt-stream fail-closed"
    )


if __name__ == "__main__":
    run()
