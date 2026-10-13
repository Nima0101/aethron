"""Bounded maximum-shape P7 measurement; synthetic software evidence only."""

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aethron.simulated_plan import SimulationPlan  # noqa: E402
from aethron.simulated_route import SimulationRoute  # noqa: E402


def run(*, route=False):
    inputs = [
        json.dumps(
            {
                "version": 1,
                "at_ms": i * 100,
                "expires_at_ms": i * 100 + 100,
                "evidence": "synthetic",
                "coordinate_frame": "synthetic_grid",
                "clock_domain": "host_monotonic_ms",
                "grid": [["free"] * 16 for _ in range(16)],
                **(
                    {"start": [0, 0], "goal": [15, 15]}
                    if route
                    else {"path": [[14 + j % 2, 15] for j in range(64)]}
                ),
            },
            separators=(",", ":"),
        ).encode()
        for i in range(100)
    ]
    samples = []
    peak = 0
    for tracing in (False, True):
        model = (SimulationRoute if route else SimulationPlan)("vehicle_stop")
        if tracing:
            tracemalloc.start()
        try:
            for i, data in enumerate(inputs):
                start = time.perf_counter()
                out = model.step(data, now_ms=i * 100)
                elapsed = (time.perf_counter() - start) * 1000
                valid = (
                    out["route_found"] and len(out["path"]) == 31
                    if route
                    else out["plan_admissible"]
                )
                if not valid or out["recommendation"]["motion_authority"]:
                    raise ValueError("invalid_probe_result")
                if not tracing:
                    samples.append(elapsed)
            if tracing:
                _, peak = tracemalloc.get_traced_memory()
        finally:
            if tracing:
                tracemalloc.stop()
            model.close()
    sources = (
        "aethron/simulated_plan.py",
        "aethron/simulated_route.py",
        "aethron/simulated_safety.py",
        "aethron/schema.py",
        "aethron/_json_bounds.py",
        "aethron/actions.py",
        "scripts/simulated_plan_probe.py",
    )
    p95 = sorted(samples)[94]
    return {
        "scope": "Synthetic maximum-shape P7 sample, not hardware or hard-real-time qualification",
        "python": platform.python_version(),
        "platform": platform.system() + " " + platform.machine(),
        "samples": 100,
        "grid_cells": 256,
        "mode": "route" if route else "assessment",
        "path_cells": 31 if route else 64,
        "workload_sha256": hashlib.sha256(b"\n".join(inputs)).hexdigest(),
        "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
        "wall_samples_ms": samples,
        "p50_ms": statistics.median(samples),
        "p95_ms": p95,
        "max_ms": max(samples),
        "peak_traced_bytes": peak,
        "p95_budget_ms": 100,
        "memory_budget_bytes": 33554432,
        "within_resource_budget": p95 <= 100 and peak <= 33554432,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "build/p6-world/plan-resource.json")
    parser.add_argument("--route", action="store_true", help="Measure bounded route generation")
    args = parser.parse_args()
    report = run(route=args.route)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in ("p95_ms", "max_ms", "peak_traced_bytes", "within_resource_budget")
            }
        )
    )
    if not report["within_resource_budget"]:
        sys.exit(1)
