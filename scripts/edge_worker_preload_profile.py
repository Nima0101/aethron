#!/usr/bin/env python3
"""Diagnostic replay-preload allocation/CPU comparison; no physical latency claim."""

import hashlib
import io
import json
import platform
import statistics
import tempfile
import threading
import time
import tracemalloc
from pathlib import Path

from aethron_edge.pipeline import _load_replay_rows

from aethron.temporal.replay import replay

ROOT = Path(__file__).resolve().parents[1]


def previous(path):
    data = path.read_bytes()
    if len(data) > 20 * 1024 * 1024:
        raise ValueError("invalid_request")
    list(replay(io.BytesIO(data)))
    return [json.loads(line) for line in data.splitlines()]


def measure(load, path, expected):
    cpu, wall = [], []
    for _ in range(3):
        start_cpu, start_wall = time.process_time_ns(), time.perf_counter_ns()
        rows = load(path)
        cpu.append((time.process_time_ns() - start_cpu) / 1e6)
        wall.append((time.perf_counter_ns() - start_wall) / 1e6)
        if rows != expected:
            raise RuntimeError("preload_parity_failed")
    tracemalloc.start()
    load(path)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "cpu_median_ms": statistics.median(cpu),
        "wall_median_ms": statistics.median(wall),
        "python_traced_peak_bytes": peak,
    }


def main():
    source = (ROOT / "examples/temporal-blackout.jsonl").read_bytes()
    rows = source.splitlines()
    # Same 24 valid frames, padded to the immutable 65536-byte per-line limit.
    padded = b"".join(line + b" " * (65535 - len(line)) + b"\n" for line in rows)
    expected = [json.loads(line) for line in rows]
    result = {
        "qualified": False,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    with tempfile.TemporaryDirectory(prefix="aethron-worker-preload-") as directory:
        path = Path(directory) / "replay.jsonl"
        path.write_bytes(padded)
        result["input_bytes"] = len(padded)
        result["input_sha256"] = hashlib.sha256(padded).hexdigest()
        result["previous"] = measure(previous, path, expected)
        result["bounded"] = measure(
            lambda p: _load_replay_rows(p, threading.Event()), path, expected
        )
    result["source_sha256"] = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in (
            "integrations/edge/aethron_edge/pipeline.py",
            "aethron/temporal/replay.py",
            "aethron/schema.py",
            "aethron/_json_bounds.py",
            "scripts/edge_worker_preload_profile.py",
        )
    }
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
