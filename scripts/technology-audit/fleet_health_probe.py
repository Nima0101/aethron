"""Bounded, synthetic audit evidence; no performance or platform qualification."""

import argparse
import hashlib
import importlib.util
import json
import platform
import resource
import statistics
import sys
import time
import tracemalloc
from pathlib import Path


def load_module(path):
    spec = importlib.util.spec_from_file_location("health_audit_subject", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def vectors():
    good = b'{"version":1,"state":"running","emitted_ms":1000,"status_expires_ms":3000}'
    cases = [("valid", good, True)]
    for label, raw, expected in [
        ("duplicate", good.replace(b'"version":1', b'"version":1,"version":1'), False),
        (
            "escaped_duplicate",
            good.replace(b'"version":1', b'"version":1,"vers\\u0069on":1'),
            False,
        ),
        ("float_version", good.replace(b'"version":1', b'"version":1.0'), False),
        ("exponent_time", good.replace(b":1000", b":1e3"), False),
        ("bool_time", good.replace(b":1000", b":true"), False),
        ("nonfinite", good.replace(b":1000", b":NaN"), False),
        ("future", good.replace(b":1000", b":1001"), False),
        ("expired", good.replace(b":3000", b":1000"), False),
        ("over_lifetime", good.replace(b":3000", b":3001"), False),
        ("extra", good.replace(b"}", b',"private":"value"}'), False),
        ("nested_state", good.replace(b'"running"', b"{}"), False),
        ("escaped_key", good.replace(b"version", b"vers\\u0069on"), True),
        ("escaped_state", good.replace(b"running", b"runn\\u0069ng"), True),
        ("whitespace_boundary", good.ljust(256), True),
        ("oversize", good.ljust(257), False),
        ("trailing_comma", good.replace(b"}", b",}"), False),
        ("trailing_value", good + b"0", False),
        ("utf8_bom", b"\xef\xbb\xbf" + good, False),
        ("invalid_utf8", b"\xff" + good, False),
        ("array", b"[]", False),
        ("null", b"null", False),
    ]:
        cases.append((label, raw, expected))
    return cases


def timing(call, iterations):
    samples = []
    for _ in range(5):
        start = time.perf_counter_ns()
        for _ in range(iterations):
            call()
        samples.append((time.perf_counter_ns() - start) / iterations / 1000)
    return {
        "unit": "microseconds",
        "iterations_per_sample": iterations,
        "samples": samples,
        "median": statistics.median(samples),
        "max_sample": max(samples),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--vectors-only", action="store_true")
    mode.add_argument("--candidate", type=Path)
    args = parser.parse_args()
    cases = vectors()
    if args.vectors_only:
        print(json.dumps([raw.hex() for _, raw, _ in cases]))
        return
    if args.module is None:
        parser.error("--module is required with --candidate")
    module = load_module(args.module)
    python_results = [module.FleetHealth(1).ingest(0, raw, now_ms=1000) for _, raw, _ in cases]
    expected = [ok for _, _, ok in cases]
    if python_results != expected:
        raise RuntimeError("production_contract_failure")
    candidate = json.loads(args.candidate.read_text())
    if candidate["strict_results"] != expected:
        raise RuntimeError("candidate_contract_failure")
    good = cases[0][1]

    def decode():
        module._validate(
            json.loads(
                good.decode("utf-8"),
                object_pairs_hook=module._pairs,
                parse_constant=module._invalid_constant,
            ),
            1000,
        )

    def sweep():
        fleet = module.FleetHealth(1024)
        for slot in range(1024):
            if not fleet.ingest(slot, good, now_ms=1000):
                raise RuntimeError("sweep_ingest_failure")
        if fleet.snapshot(now_ms=1000)["states"]["running"] != 1024:
            raise RuntimeError("sweep_snapshot_failure")

    fleet = module.FleetHealth(1024)
    for slot in range(1024):
        fleet.ingest(slot, good, now_ms=1000)
    measurements = {
        "python_decode_validate": timing(decode, 2000),
        "python_1024_ingest_and_snapshot": timing(sweep, 1),
        "python_full_snapshot": timing(lambda: fleet.snapshot(now_ms=1000), 500),
    }
    tracemalloc.start()
    traced = module.FleetHealth(1024)
    for slot in range(1024):
        traced.ingest(slot, good, now_ms=1000)
    retained, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    output = {
        "audit_policy_version": 2,
        "component": "fleet_health",
        "source_sha256": hashlib.sha256(args.module.read_bytes()).hexdigest(),
        "environment": {
            "python": platform.python_version(),
            "node": candidate["node"],
            "os": platform.system(),
            "architecture": platform.machine(),
        },
        "scope": "Synthetic single-process probes; no worst-case, contention, or hardware qualification",
        "cases": [
            {
                "name": name,
                "expected": ok,
                "python": py,
                "node_strict": js,
                "node_default_object_validation": naive,
            }
            for (name, _, ok), py, js, naive in zip(
                cases,
                python_results,
                candidate["strict_results"],
                candidate["default_results"],
                strict=True,
            )
        ],
        "measurements": measurements,
        "node_decode_validate": candidate["timing"],
        "memory": {
            "python_traced_retained_bytes": retained,
            "python_traced_peak_bytes": peak,
            "python_process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "node_process_peak_rss_kib": candidate["peak_rss_kib"],
        },
        "limitations": [
            "Node candidate covers decoder only, not state machine or thread safety.",
            "Timing excludes interpreter startup, IPC and contention; runs are not interleaved.",
            "Traced allocation excludes interpreter and native allocator overhead.",
            "Peak RSS includes probe overhead; runtimes do different work and RSS is not a ranking.",
        ],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
