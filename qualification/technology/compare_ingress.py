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
import unittest
from pathlib import Path

from aethron._json_bounds import check
from qualification.evidence import _pairs, _parse_integer, validate
from qualification.technology import source_snapshot
from qualification.technology.measurement import peak_bytes, require_result, require_untraced
from qualification.tests.test_evidence import EvidenceTests, encoded

CORPUS_SHA256 = "a62278050b822b70a4d40dd37aa51899ccc49ef5b94f1d2b4ff259299193aeff"


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
    if (
        not result.wasSuccessful()
        or not result.testsRun
        or result.skipped
        or result.expectedFailures
        or not requests
    ):
        raise RuntimeError("semantic_oracle_tests_failed")
    return requests


def _response(raw):
    """Validate an audit-only response envelope before interpreting its flag."""
    try:

        def invalid_constant(_):
            raise ValueError("invalid_audit_response")

        row = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_int=_parse_integer,
            parse_constant=invalid_constant,
        )
        if type(row) is not dict or type(row.get("accepted")) is not bool:
            raise ValueError("invalid_audit_response")
        keys = {"accepted", "document"} if row["accepted"] else {"accepted"}
        if set(row) != keys:
            raise ValueError("invalid_audit_response")
        return row
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid_audit_response") from None


def _document_matches(raw, document):
    """Compare decoded values, not lossy summaries or original JSON spelling."""
    try:
        if not check(raw):
            return False
        original = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_pairs, parse_int=_parse_integer
        )
        # Sorting ignores object order; encoding distinguishes 1, 1.0 and true.
        # Finite floats retain Python's decoded value, not their source spelling.
        return json.dumps(original, sort_keys=True, allow_nan=False) == json.dumps(
            document, sort_keys=True, allow_nan=False
        )
    except (ValueError, UnicodeError, RecursionError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--export", action="store_true")
    mode.add_argument("--responses", type=Path)
    args = parser.parse_args()
    if not args.export:
        require_untraced()
    root = Path(__file__).parent
    sources = source_snapshot.capture(
        root.parent.parent,
        (
            "qualification/technology/IngressProbe.java",
            "qualification/technology/compare_ingress.py",
            "qualification/technology/measurement.py",
            "qualification/technology/ingress-vectors-v1.json",
            "qualification/evidence.py",
            "aethron/_json_bounds.py",
            "qualification/rigs/synthetic-v1.json",
            "qualification/tests/test_evidence.py",
            "qualification/technology/source_snapshot.py",
        ),
    )
    vector_bytes = (root / "ingress-vectors-v1.json").read_bytes()
    if hashlib.sha256(vector_bytes).hexdigest() != CORPUS_SHA256:
        raise RuntimeError("invalid_ingress_corpus")
    vectors = json.loads(vector_bytes)
    requests = [(bytes.fromhex(row["hex"]), 1050) for row in vectors] + collect()
    transport = "\n".join(raw.hex() for raw, _ in requests) + "\n"
    if len(requests) > 256 or len(transport) > 8 * 1024 * 1024:
        raise RuntimeError("audit_transport_budget")
    if args.export:
        source_snapshot.verify(root.parent.parent, sources)
        print(transport, end="")
        return 0
    with args.responses.open("rb") as source:
        response_bytes = source.read(8 * 1024 * 1024 + 1)
    if len(response_bytes) > 8 * 1024 * 1024:
        raise RuntimeError("audit_response_budget")
    lines = response_bytes.splitlines()
    if len(lines) != len(requests):
        raise RuntimeError("audit_row_count")
    rows = [_response(row) for row in lines]
    # Equal downstream schema errors do not prove correct token admission.
    # Only the pinned ingress corpus declares this independent expectation;
    # collected semantic requests are not a second ingress specification.
    ingress_mismatches = [
        index
        for index, (vector, row) in enumerate(zip(vectors, rows))
        if row["accepted"] is not (not vector["reject"])
    ]
    report_mismatches, document_mismatches = [], []
    for index, ((raw, now_ms), row) in enumerate(zip(requests, rows)):
        expected = outcome(raw, now_ms)
        actual = {"error": "invalid_qualification_manifest"}
        if row["accepted"]:
            if not _document_matches(raw, row["document"]):
                document_mismatches.append(index)
            actual = outcome(encoded(row["document"]), now_ms)
            if "input_sha256" in actual:
                actual["input_sha256"] = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            report_mismatches.append(index)
    mismatches = sorted(set(ingress_mismatches) | set(report_mismatches) | set(document_mismatches))

    # Local upper-byte-bound measurement, not an acceptance threshold or a
    # cross-language timing comparison. No compilation or unbounded soak.
    baseline = (root.parent / "rigs/synthetic-v1.json").read_bytes()
    padded = baseline + b" " * (65536 - len(baseline))
    # Authored from the reviewed synthetic fixture, not from validate's result.
    expected_measurement = {
        "version": 1,
        "input_sha256": "5ecd7409628816cfb0cdd497fa0ff1f85b0f3340fdf6ec4870c8021c04c53f66",
        "declaration_checks_passed": True,
        "sensor_count": 2,
        "record_count": 6,
        "evidence_counts": {"synthetic": 6, "recorded": 0, "external_unverified": 0},
        "findings": [],
        "artifacts_verified": False,
        "physical_qualification_passed": False,
        "physical_status": "blocked_external_evidence_and_review",
    }
    samples = []
    for _ in range(20):
        start = time.perf_counter_ns()
        measured = validate(padded, now_ms=1050)
        samples.append(time.perf_counter_ns() - start)
        require_result(measured, expected_measurement, "ingress_measurement_failed")
    traced_result = None

    def traced_validate():
        nonlocal traced_result
        traced_result = validate(padded, now_ms=1050)

    peak = peak_bytes(traced_validate)
    require_result(traced_result, expected_measurement, "ingress_measurement_failed")
    source_snapshot.verify(root.parent.parent, sources)
    report = {
        "audit_policy_version": 3,
        "scope": "Java ingress with unchanged Python semantic oracle; not a Java validator",
        "python": platform.python_version(),
        "ingress_cases": len(vectors),
        "semantic_requests": len(requests) - len(vectors),
        "mismatch_indices": mismatches,
        "ingress_mismatch_indices": ingress_mismatches,
        "report_mismatch_indices": report_mismatches,
        "document_mismatch_indices": document_mismatches,
        "all_reports_match": not report_mismatches,
        "all_ingress_expectations_match": not ingress_mismatches,
        "all_documents_match": not document_mismatches,
        "request_transport_sha256": hashlib.sha256(transport.encode("ascii")).hexdigest(),
        "response_transport_sha256": hashlib.sha256(response_bytes).hexdigest(),
        "python_65536_byte_measurement": {
            "iterations": len(samples),
            "elapsed_ns": samples,
            "traced_peak_bytes_one_call": peak,
            "acceptance_threshold": None,
            "all_measured_results_checked": True,
            "result_validation_excluded_from_measurements": True,
            "expected_input_sha256": expected_measurement["input_sha256"],
        },
        "source_sha256": sources,
        "source_observation": "equal_before_and_after_workload",
        "physical_qualification_passed": False,
    }
    print(json.dumps(report, indent=2))
    return int(bool(mismatches))


if __name__ == "__main__":
    raise SystemExit(main())
