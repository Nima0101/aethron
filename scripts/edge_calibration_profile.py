#!/usr/bin/env python3
"""Diagnostic calibration admission comparison; no physical qualification claim."""

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
import tracemalloc
import unittest
from pathlib import Path
from typing import Annotated
from unittest.mock import patch

from aethron_edge.calibration import CalibrationRecord
from aethron_edge.sources.base import FrameEnvelope
from pydantic import BeforeValidator, Field, StrictFloat, StrictInt, TypeAdapter, ValidationError


def json_number(value):
    if type(value) not in (int, float):
        raise ValueError("invalid_number")
    return value


Identity = Annotated[str, Field(strict=True, min_length=1)]
Dimension = Annotated[int, Field(strict=True, gt=0)]
Timestamp = Annotated[int, Field(strict=True, ge=0)]
Real = Annotated[StrictInt | StrictFloat, BeforeValidator(json_number)]
Transform = Annotated[tuple[Real, ...], Field(min_length=9, max_length=9)]
Residual = Annotated[Real, Field(ge=0, le=0.05)]
ADAPTER = TypeAdapter(
    tuple[
        Identity,
        Dimension,
        Dimension,
        Timestamp,
        Identity,
        Transform,
        Residual,
        Dimension,
        Dimension,
        Identity,
        Timestamp,
        Identity,
    ]
)


def compiled_schema(record, frame, now, mount):
    try:
        values = ADAPTER.validate_python(
            (
                record.calibration_id,
                record.width,
                record.height,
                record.valid_until_ms,
                record.mount_id,
                record.transform,
                record.residual,
                frame.width,
                frame.height,
                frame.calibration_id,
                now,
                mount,
            ),
            strict=True,
        )
    except ValidationError:
        return False
    cid, w, h, until, mid, transform, _, fw, fh, fcid, at, rig = values
    return (
        cid == fcid
        and (w, h) == (fw, fh)
        and mid == rig
        and at <= until
        and transform == (1, 0, 0, 0, 1, 0, 0, 0, 1)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conformance-tests", type=Path, required=True)
    args = parser.parse_args()
    # Apply the identical behavioral suite to the candidate, including build_v3.
    suite = unittest.defaultTestLoader.discover(
        str(args.conformance_tests), pattern="test_calibration_admission.py"
    )
    if suite.countTestCases() == 0:
        raise RuntimeError("missing_calibration_tests")
    with patch.object(CalibrationRecord, "valid_for", compiled_schema):
        result = unittest.TextTestRunner(stream=sys.stderr).run(suite)
    if not result.wasSuccessful():
        raise RuntimeError("calibration_candidate_parity_failed")
    record = CalibrationRecord("bench", 2, 2, 2000, "mount-a", (1, 0, 0, 0, 1, 0, 0, 0, 1), 0.001)
    frame = FrameEnvelope(b"\0" * 12, 2, 2, 1, 0, 0, "host_monotonic", 0, "bench")
    gates = {
        "python": lambda: record.valid_for(frame, 1000, "mount-a"),
        "pydantic_core": lambda: compiled_schema(record, frame, 1000, "mount-a"),
    }
    samples = {name: [] for name in gates}
    for batch in range(5):
        for name in list(gates)[:: 1 if batch % 2 else -1]:
            gate = gates[name]
            if gate() is not True:
                raise RuntimeError("valid_calibration_rejected")
            start = time.process_time_ns()
            for _ in range(10000):
                gate()
            samples[name].append((time.process_time_ns() - start) / 10000)
    peaks = {}
    for name, gate in gates.items():
        tracemalloc.start()
        for _ in range(100):
            gate()
        _, peaks[name] = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    root = Path(__file__).resolve().parents[1]
    print(
        json.dumps(
            {
                "qualified": False,
                "python": platform.python_version(),
                "platform": platform.platform(),
                "cpu_ns_per_call": samples,
                "candidate_conformance_tests": result.testsRun,
                "python_traced_peak_bytes": peaks,
                "median_cpu_ns_per_call": {k: statistics.median(v) for k, v in samples.items()},
                "source_sha256": {
                    p: hashlib.sha256((root / p).read_bytes()).hexdigest()
                    for p in (
                        "integrations/edge/aethron_edge/calibration.py",
                        "scripts/edge_calibration_profile.py",
                    )
                },
            },
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
