"""Diagnostic scalar admission comparison, not runtime latency qualification."""

import hashlib
import json
import statistics
import time
from pathlib import Path

from pydantic_core import SchemaValidator, ValidationError, core_schema


def exact(value):
    if type(value) is not int:
        raise ValueError("clock_untrusted")
    return value


schema = SchemaValidator(
    core_schema.tuple_positional_schema(
        [
            core_schema.no_info_before_validator_function(
                exact, core_schema.int_schema(strict=True, ge=0)
            )
        ]
        * 3
    )
)


def direct(values):
    return not any(type(value) is not int or value < 0 for value in values)


def native(values):
    try:
        schema.validate_python(values)
        return True
    except ValidationError:
        return False


cases = [((0, 0, 0), True), ((2**100, 0, 2**100), True)]
for x in (True, False, -1, 0.0, None, "0"):
    for index in range(3):
        values = [0, 0, 0]
        values[index] = x
        cases.append((tuple(values), False))
for fn in (direct, native):
    for args, expected in cases:
        if fn(args) is not expected:
            raise RuntimeError(f"{fn.__name__}: admission parity failure")
samples = {}
for fn in (direct, native):
    timings = []
    for _ in range(5):
        start = time.process_time_ns()
        for _iteration in range(10000):
            fn((1_000_000_000, 0, 1_000_000_000))
        timings.append((time.process_time_ns() - start) / 10000)
    samples[fn.__name__] = timings
print(
    json.dumps(
        {
            "cases_per_candidate": len(cases),
            "cpu_ns": samples,
            "median_cpu_ns": {k: statistics.median(v) for k, v in samples.items()},
            "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        },
        indent=2,
    )
)
