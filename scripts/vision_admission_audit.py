"""Bounded native/NumPy admission comparison; excludes inference and hardware qualification."""

import hashlib
import json
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from unittest.mock import patch

import numpy as np
from aethron_vision_native import CONTRACT_VERSION

from aethron.vision.yolox import _validated_output


def legacy_numpy(raw):
    if not np.isfinite(raw).all():
        raise ValueError("invalid_input")
    probabilities = raw[0, :, 4:]
    if not ((probabilities >= 0).all() and (probabilities <= 1).all()):
        raise ValueError("invalid_input")
    return raw[0]


def accepted(check, raw):
    try:
        check(raw)
    except ValueError:
        return False
    return True


def measure(check, raw):
    check(raw)
    samples, cpu_samples = [], []
    for _ in range(5):
        start, cpu = time.perf_counter_ns(), time.process_time_ns()
        check(raw)
        cpu_samples.append(time.process_time_ns() - cpu)
        samples.append(time.perf_counter_ns() - start)
    tracemalloc.start()
    try:
        check(raw)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {
        "samples_ns": samples,
        "median_ns": int(statistics.median(samples)),
        "cpu_samples_ns": cpu_samples,
        "cpu_median_ns": int(statistics.median(cpu_samples)),
        "traced_peak_bytes": peak,
    }


def main():
    if CONTRACT_VERSION != 1:
        raise RuntimeError("native_contract_mismatch")
    root = Path(__file__).resolve().parents[1]
    report = {
        "audit_policy_version": 2,
        "qualified": False,
        "scope": "synthetic output admission; no inference, hardware or capacity claim",
        "memory_scope": "traced scratch only, excluding input; not RSS or native heap accounting",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "source_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in (
                "aethron/vision/yolox.py",
                "integrations/native-vision/aethron_vision_native/bounds.c",
                "scripts/vision_admission_audit.py",
            )
        },
        "layouts": {},
        "parity_checks": 0,
    }
    raw = np.full((1, 8400, 85), 0.5, dtype=np.float32)
    for name, data in (
        ("c_contiguous", raw),
        ("fortran", np.asfortranarray(raw)),
        ("reversed", raw[:, ::-1, ::-1]),
    ):
        cases = [(0, 0, 0.0, True), (8399, 84, 1.0, True)]
        for column in (0, 3, 4, 84):
            cases.extend((8399, column, value, False) for value in (np.nan, np.inf, -np.inf))
        cases.extend(
            (8399, 84, value, False)
            for value in (
                np.nextafter(np.float32(0), np.float32(-1)),
                np.nextafter(np.float32(1), np.float32(2)),
            )
        )
        for row, column, value, expected in cases:
            data[0, row, column] = value
            outcomes = [accepted(legacy_numpy, data), accepted(_validated_output, data)]
            with patch.dict(sys.modules, {"aethron_vision_native": None}):
                outcomes.append(accepted(_validated_output, data))
            if outcomes != [expected] * 3:
                raise RuntimeError("admission_parity_failed")
            report["parity_checks"] += 3
            data[0, row, column] = 0.5
        measurements = {"legacy_numpy": measure(legacy_numpy, data)}
        with patch.dict(sys.modules, {"aethron_vision_native": None}):
            measurements["portable_numpy"] = measure(_validated_output, data)
        measurements["selected"] = measure(_validated_output, data)
        measurements["selected_backend"] = "native" if data.flags.c_contiguous else "numpy"
        report["layouts"][name] = measurements
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
