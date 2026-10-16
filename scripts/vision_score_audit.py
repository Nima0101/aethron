"""Small deterministic score-only parity and timing comparison; no inference claims."""

import hashlib
import json
import platform
import statistics
import time
from pathlib import Path

import aethron_vision_native as native
import numpy as np

from aethron.vision.yolox import _selected_scores


def numpy_scores(raw):
    values = raw[0]
    scores = values[:, 4, None] * values[:, 5:]
    categories = np.argmax(scores, axis=1)
    return categories, scores[np.arange(8400), categories]


def chunked_scores(raw):
    categories = np.empty(8400, dtype=np.intp)
    confidence = np.empty(8400, dtype=np.float32)
    for start in range(0, 8400, 512):
        values = raw[0, start : start + 512]
        scores = values[:, 4, None] * values[:, 5:]
        indices = scores.argmax(axis=1)
        categories[start : start + 512] = indices
        confidence[start : start + 512] = scores[np.arange(len(values)), indices]
    return categories, confidence


def main():
    if native.SCORE_CONTRACT_VERSION != 1:
        raise ValueError("score contract 1 required")
    rng = np.random.default_rng(20261010)
    methods = {"numpy": numpy_scores, "chunked_numpy": chunked_scores, "selected": _selected_scores}
    cases = {}
    for case in ("random", "ties", "subnormal"):
        raw = rng.random((1, 8400, 85), dtype=np.float32)
        if case == "ties":
            raw[:, :, 4:] = 0.75
        elif case == "subnormal":
            raw[:, :, 4] = np.nextafter(np.float32(0), np.float32(1))
        with np.errstate(under="ignore"):
            expected = numpy_scores(raw)
            timings = {name: {"wall_ns": [], "cpu_ns": []} for name in methods}
            for sample in range(6):
                order = list(methods) if sample % 2 else list(reversed(methods))
                for name in order:
                    wall, cpu = time.perf_counter_ns(), time.process_time_ns()
                    actual = methods[name](raw)
                    cpu, wall = time.process_time_ns() - cpu, time.perf_counter_ns() - wall
                    np.testing.assert_array_equal(actual[0], expected[0])
                    np.testing.assert_array_equal(
                        actual[1].view(np.uint32), expected[1].view(np.uint32)
                    )
                    if sample:
                        timings[name]["wall_ns"].append(wall)
                        timings[name]["cpu_ns"].append(cpu)
            for timing in timings.values():
                timing["median_cpu_ns"] = statistics.median(timing["cpu_ns"])
                timing["median_wall_ns"] = statistics.median(timing["wall_ns"])
            cases[case] = timings
    sources = [
        "scripts/vision_score_audit.py",
        "aethron/vision/yolox.py",
        "integrations/native-vision/aethron_vision_native/bounds.c",
        "integrations/native-vision/setup.py",
    ]
    print(
        json.dumps(
            {
                "schema_version": 1,
                "audit_policy_version": 2,
                "qualified": False,
                "scope": "Score reduction only; native includes independent full tensor admission; provider and geometry excluded.",
                "python": platform.python_version(),
                "numpy": np.__version__,
                "platform": platform.platform(),
                "source_sha256": {
                    name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in sources
                },
                "cases": cases,
                "parity_comparisons": 54,
                "allocation_payload_bytes": {
                    "legacy_product_matrix": 2688000,
                    "native_returned_bytes": 42000,
                },
                "allocation_note": "Array/byte payload calculation, not RSS measurement; interpreter and input buffers excluded.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
