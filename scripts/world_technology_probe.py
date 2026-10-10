"""Bounded v3/P6 resource comparison for technology reassessment; no field claims."""

import argparse
import hashlib
import json
import math
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aethron.temporal import Session  # noqa: E402
from aethron.temporal.fixtures import detection, encode, frame  # noqa: E402
from aethron.world import CLOCK_DOMAIN, COORDINATE_FRAME, WorldModel  # noqa: E402


def summarize(samples, peak):
    if (
        len(samples) != 100
        or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in samples)
        or type(peak) is not int
        or peak < 0
    ):
        raise ValueError("invalid_measurement")
    p95 = sorted(samples)[94]
    return {
        "frames": 100,
        "objects": 32,
        "p50_ms": statistics.median(samples),
        "p95_ms": p95,
        "max_ms": max(samples),
        "peak_traced_bytes": peak,
        "p95_budget_ms": 100,
        "memory_budget_bytes": 32 * 1024 * 1024,
        "within_frozen_resource_budget": p95 <= 100 and peak <= 32 * 1024 * 1024,
        "wall_samples_ms": samples,
    }


def step(model, data, now):
    if isinstance(model, WorldModel):
        out = model.step(
            data, now_ms=now, coordinate_frame=COORDINATE_FRAME, clock_domain=CLOCK_DOMAIN
        )["scene"]
    else:
        out = model.step(data, now_ms=now)
    if len(out["tracks"]) != 32 or any(t["status"] != "PRESENT" for t in out["tracks"]):
        raise ValueError("lost_current_evidence")


def measure(factory, inputs):
    model = factory()
    wall, cpu = [], []
    try:
        for i, data in enumerate(inputs):
            wall_start, cpu_start = time.perf_counter(), time.process_time()
            step(model, data, i * 100)
            wall.append((time.perf_counter() - wall_start) * 1000)
            cpu.append((time.process_time() - cpu_start) * 1000)
    finally:
        model.close()
    model = factory()
    tracemalloc.start()
    try:
        for i, data in enumerate(inputs):
            step(model, data, i * 100)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
        model.close()
    return dict(summarize(wall, peak), cpu_p95_ms_diagnostic_only=sorted(cpu)[94])


def run():
    # Same fixed workload as scripts/temporal_evaluate.py; thresholds unchanged.
    inputs = [
        encode(
            frame(
                i * 100,
                [
                    detection(0.03 + (j % 8) * 0.12, y=0.1 + (j // 8) * 0.2, w=0.03, h=0.04)
                    for j in range(32)
                ],
            )
        )
        for i in range(100)
    ]
    sources = [
        "aethron/world.py",
        "aethron/temporal/session.py",
        "aethron/temporal/fusion.py",
        "aethron/temporal/math.py",
        "aethron/temporal/schema.py",
        "aethron/schema.py",
        "aethron/_json_bounds.py",
        "scripts/world_technology_probe.py",
    ]
    return {
        "audit_policy_version": 2,
        "scope": "Synthetic software resource sample; not hardware, WCET or release qualification",
        "python": platform.python_version(),
        "platform": platform.system() + " " + platform.machine(),
        "workload_sha256": hashlib.sha256(b"\n".join(inputs)).hexdigest(),
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources
        },
        "session": measure(Session, inputs),
        "world": measure(WorldModel, inputs),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "build/p6-world/technology-probe.json")
    args = parser.parse_args()
    report = run()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "source_sha256"}))
    # Evidence is written before failure. Do not tune a threshold or discard a run.
    if not all(report[k]["within_frozen_resource_budget"] for k in ("session", "world")):
        sys.exit(1)
