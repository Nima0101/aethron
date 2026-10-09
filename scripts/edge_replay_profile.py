"""Reproduce P1.1 input-allocation and CPU evidence; no qualification threshold."""

import argparse
import cProfile
import gc
import hashlib
import importlib.metadata
import json
import platform
import pstats
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path

import aethron_edge
from aethron_edge.protocol import replay_bytes, replay_stream

import aethron


def fingerprint(report):
    data = json.dumps(report.model_dump(by_alias=True), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()


def legacy(stream):
    return replay_bytes(stream.read(20 * 1024 * 1024 + 1))


def measure(path, consumer, samples):
    wall, cpu, digests = [], [], set()
    for _ in range(samples):
        gc.collect()
        with path.open("rb") as stream:
            started, cpu_started = time.perf_counter_ns(), time.process_time_ns()
            report = consumer(stream)
            cpu.append((time.process_time_ns() - cpu_started) / 1e6)
            wall.append((time.perf_counter_ns() - started) / 1e6)
        digests.add(fingerprint(report))
        del report
    gc.collect()
    tracemalloc.start()
    try:
        with path.open("rb") as stream:
            report = consumer(stream)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    digests.add(fingerprint(report))
    if len(digests) != 1:
        raise RuntimeError("nondeterministic_replay")
    return {
        "cpu_ms": cpu,
        "cpu_median_ms": statistics.median(cpu),
        "wall_ms": wall,
        "wall_median_ms": statistics.median(wall),
        "python_traced_peak_bytes": peak,
        "report_sha256": digests.pop(),
        "frame_count": report.frame_count,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, choices=range(1, 301), default=300)
    parser.add_argument("--samples", type=int, choices=range(1, 6), default=3)
    args = parser.parse_args()
    # Maximum legal line width, minimal synthetic scene: isolates input cost.
    frame = {
        "version": 3,
        "at_ms": 0,
        "lighting": "daylight",
        "evidence": "synthetic",
        "mode": "direct",
        "contract": "warn",
        "scene_break": False,
        "sensors": [],
        "ego": {"dx": 0, "dy": 0, "variance": 0, "valid": False},
    }
    with tempfile.TemporaryDirectory(prefix="aethron-replay-profile-") as directory:
        path = Path(directory) / "synthetic.jsonl"
        with path.open("wb") as stream:
            for i in range(args.frames):
                frame["at_ms"] = i * 99
                line = json.dumps(frame, separators=(",", ":")).encode()
                stream.write(line + b" " * (65535 - len(line)) + b"\n")
        results = {
            name: measure(path, fn, args.samples)
            for name, fn in (("whole_file", legacy), ("bounded_lines", replay_stream))
        }
        if results["whole_file"]["report_sha256"] != results["bounded_lines"]["report_sha256"]:
            raise RuntimeError("replay_parity_failed")
        profile = cProfile.Profile()
        with path.open("rb") as stream:
            profile.runcall(replay_stream, stream)
        stats = pstats.Stats(profile)
        hot = sorted(stats.stats.items(), key=lambda item: item[1][2], reverse=True)[:8]
        input_bytes = path.stat().st_size
    sources = {}
    for package in (aethron, aethron_edge):
        root = Path(package.__file__).parent
        for source in sorted(root.rglob("*.py")):
            sources[f"{package.__name__}/{source.relative_to(root).as_posix()}"] = hashlib.sha256(
                source.read_bytes()
            ).hexdigest()
    print(
        json.dumps(
            {
                "qualified": False,
                "technology_audit": "P1.1 comparison pending",
                "workload": "synthetic empty scene, 65536-byte whitespace-padded lines",
                "input_bytes": input_bytes,
                "python": platform.python_version(),
                "os": platform.system(),
                "machine": platform.machine(),
                "pydantic": importlib.metadata.version("pydantic"),
                "results": results,
                "profile_self_seconds": [
                    {
                        "file": Path(key[0]).name,
                        "function": key[2],
                        "calls": value[1],
                        "seconds": value[2],
                    }
                    for key, value in hot
                ],
                "source_sha256": sources,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
