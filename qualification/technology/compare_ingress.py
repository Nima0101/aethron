"""Bounded Java ingress experiment with the unchanged Python semantic oracle.

Run as a module from the source checkout. This is audit tooling, not admission
code. Export requests, run the compiled Java probe, then compare its responses.
"""

import argparse
import hashlib
import io
import json
import platform
import time
import tracemalloc
import unittest
from pathlib import Path

from qualification.evidence import validate
from qualification.tests.test_evidence import EvidenceTests, encoded


def outcome(raw, now_ms):
    try:
        return validate(raw, now_ms=now_ms)
    except ValueError:
        return {"error": "invalid_qualification_manifest"}


def collect():
    requests = []

    class Capture(EvidenceTests):
        def validate(self, doc, now_ms=1050):
            raw = doc if type(doc) is bytes else encoded(doc)
            requests.append((raw, now_ms))
            return super().validate(doc, now_ms)

    names = unittest.defaultTestLoader.getTestCaseNames(EvidenceTests)
    # The existing finite scalar cross-product stays in the normal unit suite.
    names.remove("test_wrong_scalar_types_at_every_leaf_fail_closed")
    result = unittest.TextTestRunner(stream=io.StringIO()).run(
        unittest.TestSuite(Capture(name) for name in names)
    )
    if not result.wasSuccessful():
        raise RuntimeError("semantic_oracle_tests_failed")
    return requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--export", action="store_true")
    mode.add_argument("--responses", type=Path)
    args = parser.parse_args()
    root = Path(__file__).parent
    vectors = json.loads((root / "ingress-vectors-v1.json").read_text())
    requests = [(bytes.fromhex(row["hex"]), 1050) for row in vectors] + collect()
    transport = "\n".join(raw.hex() for raw, _ in requests) + "\n"
    if len(requests) > 256 or len(transport) > 8 * 1024 * 1024:
        raise RuntimeError("audit_transport_budget")
    if args.export:
        print(transport, end="")
        return 0
    with args.responses.open("rb") as source:
        response_bytes = source.read(8 * 1024 * 1024 + 1)
    if len(response_bytes) > 8 * 1024 * 1024:
        raise RuntimeError("audit_response_budget")
    rows = [json.loads(row) for row in response_bytes.splitlines()]
    if len(rows) != len(requests):
        raise RuntimeError("audit_row_count")
    mismatches = []
    for index, ((raw, now_ms), row) in enumerate(zip(requests, rows)):
        expected = outcome(raw, now_ms)
        actual = {"error": "invalid_qualification_manifest"}
        if row["accepted"]:
            actual = outcome(encoded(row["document"]), now_ms)
            if "input_sha256" in actual:
                actual["input_sha256"] = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            mismatches.append(index)

    # Local upper-byte-bound measurement, not an acceptance threshold or a
    # cross-language timing comparison. No compilation or unbounded soak.
    baseline = (root.parent / "rigs/synthetic-v1.json").read_bytes()
    padded = baseline + b" " * (65536 - len(baseline))
    samples = []
    for _ in range(20):
        start = time.perf_counter_ns()
        validate(padded, now_ms=1050)
        samples.append(time.perf_counter_ns() - start)
    tracemalloc.start()
    validate(padded, now_ms=1050)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report = {
        "audit_policy_version": 2,
        "scope": "Java ingress with unchanged Python semantic oracle; not a Java validator",
        "python": platform.python_version(),
        "ingress_cases": len(vectors),
        "semantic_requests": len(requests) - len(vectors),
        "mismatch_indices": mismatches,
        "all_reports_match": not mismatches,
        "request_transport_sha256": hashlib.sha256(transport.encode("ascii")).hexdigest(),
        "response_transport_sha256": hashlib.sha256(response_bytes).hexdigest(),
        "python_65536_byte_measurement": {
            "iterations": len(samples),
            "elapsed_ns": samples,
            "traced_peak_bytes_one_call": peak,
            "acceptance_threshold": None,
        },
        "source_sha256": {
            str(path.relative_to(root.parent.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                root / "IngressProbe.java",
                root / "compare_ingress.py",
                root / "ingress-vectors-v1.json",
                root.parent / "evidence.py",
                root.parent / "tests/test_evidence.py",
            )
        },
        "physical_qualification_passed": False,
    }
    print(json.dumps(report, indent=2))
    return int(bool(mismatches))


if __name__ == "__main__":
    raise SystemExit(main())
