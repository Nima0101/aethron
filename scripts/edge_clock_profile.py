#!/usr/bin/env python3
"""Clock scalar parity and diagnostic CPU profile; optional trusted native probe.

Build scripts/probes/clock_compatibility.rs with rustc --crate-type cdylib -O
--edition=2021 -D warnings -o LIBRARY, then pass --native-library LIBRARY.
The native wrapper checks types/ranges before FFI and preserves large integers.
No hard latency, native memory bound, or appliance qualification is asserted.
"""

import argparse
import ctypes
import hashlib
import json
import platform
import random
import statistics
import time
from pathlib import Path

from aethron_edge.timebase import CaptureClock

ROOT = Path(__file__).resolve().parents[1]
U64_MAX = 2**64 - 1


def native_gate(path):
    library = ctypes.CDLL(str(path.resolve()))
    function = library.compatible
    function.argtypes = [ctypes.c_uint64] * 4
    function.restype = ctypes.c_uint8

    def compatible(a, ae, b, be):
        if any(type(v) is not int or v < 0 for v in (a, ae, b, be)):
            return False
        if any(v > U64_MAX for v in (a, ae, b, be)):
            return abs(a - b) + ae + be <= 50_000_000
        return bool(function(a, ae, b, be))

    return compatible


def cases():
    # Includes conversion/wrap traps and the one-nanosecond boundary in both orders.
    rows = []
    for base in (0, 2**53, U64_MAX - 50_000_000, U64_MAX, 2**128):
        for delta in (-1, 0, 1):
            a, b = base, base + 40_000_000 + delta
            rows.extend(
                [
                    ((a, 4_000_000, b, 6_000_000), delta <= 0),
                    ((b, 6_000_000, a, 4_000_000), delta <= 0),
                ]
            )
    for value in (True, False, -1, 0.0, 0.5, float("nan"), float("inf"), None, "0"):
        for index in range(4):
            args = [0, 0, 0, 0]
            args[index] = value
            rows.append((tuple(args), False))
    rows.extend(
        [
            ((0, 1, U64_MAX, 0), False),
            ((0, U64_MAX, 0, U64_MAX), False),
            ((0, 2**128, 0, 0), False),
        ]
    )
    # Reproducible test vectors, never secrets.
    rng = random.Random(13)  # nosec B311
    for _ in range(2000):
        a = rng.randrange(U64_MAX - 100_000_000)
        b = a + rng.randrange(100_000_000)
        ae, be = rng.randrange(25_000_000), rng.randrange(25_000_000)
        rows.append(((a, ae, b, be), b - a <= 50_000_000 - ae - be))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-library", type=Path)
    args = parser.parse_args()
    gates = {"python": CaptureClock.compatible}
    if args.native_library:
        gates["rust_ctypes_with_guards"] = native_gate(args.native_library)
    vectors = cases()
    for name, gate in gates.items():
        for values, expected in vectors:
            if gate(*values) is not expected:
                raise RuntimeError(f"clock_parity_failed:{name}")
    workload = [(10**15, 4_000_000, 10**15 + 40_000_000 + d, 6_000_000) for d in (-1, 0, 1)]
    measurements = {name: [] for name in gates}
    # Alternate order to reduce systematic warmup/load bias on the shared machine.
    for batch in range(5):
        names = list(gates) if batch % 2 else list(reversed(gates))
        for name in names:
            gate = gates[name]
            start = time.process_time_ns()
            for i in range(30000):
                gate(*workload[i % len(workload)])
            measurements[name].append((time.process_time_ns() - start) / 30000)
    result = {
        "qualified": False,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "parity_cases_per_implementation": len(vectors),
        "iterations_per_batch": 30000,
        "cpu_ns_per_call": measurements,
        "median_cpu_ns_per_call": {k: statistics.median(v) for k, v in measurements.items()},
        "source_sha256": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "integrations/edge/aethron_edge/timebase.py",
                "scripts/edge_clock_profile.py",
                "scripts/probes/clock_compatibility.rs",
            )
        },
    }
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
