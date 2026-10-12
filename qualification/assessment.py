"""Compose bounded raw qualification inputs without accepting approval reports."""

import hashlib
import json

from .artifacts import MAX_ARTIFACT_BYTES, MAX_ARTIFACTS, MAX_TOTAL_BYTES
from .artifacts import verify as verify_artifacts
from .campaign import MAX_CAPTURES, _inputs
from .campaign import evaluate as evaluate_coverage
from .domains import validate as validate_domain
from .evidence import _hash, _keys
from .methods import MAX_METHOD_BYTES, MAX_METHODS
from .methods import verify as verify_methods


def _require(condition):
    if not condition:
        raise ValueError("invalid_qualification_assessment")


def _byte_map(value, count, size):
    _require(type(value) is dict and len(value) <= count)
    result = value.copy()
    _require(len(result) <= count)
    for key, raw in result.items():
        _hash(key)
        _require(type(raw) is bytes and len(raw) <= size)
    return result


def _snapshot(plan_bytes, captures, methods):
    _require(type(captures) is list and len(captures) <= MAX_CAPTURES)
    submitted = captures.copy()
    _require(len(submitted) <= MAX_CAPTURES)
    rows, artifacts, total = [], [], 0
    for item in submitted:
        _require(type(item) is dict)
        row = item.copy()
        _keys(row, "case_id manifest now_ms artifacts")
        supplied = _byte_map(row.pop("artifacts"), MAX_ARTIFACTS, MAX_ARTIFACT_BYTES)
        total += sum(map(len, supplied.values()))
        _require(total <= MAX_TOTAL_BYTES)
        rows.append(row)
        artifacts.append(supplied)
    # Validate primitive values before any component can consume the snapshot.
    _inputs(plan_bytes, rows)
    return rows, artifacts, _byte_map(methods, MAX_METHODS, MAX_METHOD_BYTES)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _commitment(plan, domain, procedure, method_report, rows, artifacts):
    bindings = sorted(
        [
            row["case_id"],
            _sha(row["manifest"]),
            row["now_ms"],
            sorted([key, _sha(raw)] for key, raw in supplied.items()),
        ]
        for row, supplied in zip(rows, artifacts)
    )
    return _sha(
        b"aethron.qualification.assessment.v1\0"
        + json.dumps(
            [_sha(plan), _sha(domain), _sha(procedure), method_report["methods_sha256"], bindings],
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
    )


def evaluate(plan_bytes, captures, domain_bytes, procedure_bytes, methods):
    """Retain all admitted gate outcomes; byte consistency never grants authority."""
    try:
        rows, artifacts, supplied_methods = _snapshot(plan_bytes, captures, methods)
        coverage = evaluate_coverage(plan_bytes, rows)
        domain = validate_domain(plan_bytes, domain_bytes)
        method_report = verify_methods(plan_bytes, procedure_bytes, supplied_methods)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid_qualification_assessment") from None

    reports = []
    for index, (row, supplied) in enumerate(zip(rows, artifacts)):
        findings, report = [], None
        try:
            report = verify_artifacts(row["manifest"], supplied, now_ms=row["now_ms"])
        except ValueError:
            # Envelope already admitted; malformed capture content is retained.
            findings = ["capture_invalid"]
        reports.append({"capture_index": index, "findings": findings, "report": report})
    bytes_verified = bool(reports) and all(
        row["report"] is not None and row["report"]["artifact_bytes_verified"] for row in reports
    )
    captures_passed = bool(reports) and all(
        row["report"] is not None and row["report"]["software_checks_passed"] for row in reports
    )
    return {
        "version": 1,
        "submission_sha256": _commitment(
            plan_bytes, domain_bytes, procedure_bytes, method_report, rows, artifacts
        ),
        "coverage": coverage,
        "domain": domain,
        "methods": method_report,
        "captures": reports,
        "artifact_bytes_verified": bytes_verified,
        "software_checks_passed": (
            coverage["declaration_coverage_complete"]
            and domain["domain_declaration_checks_passed"]
            and method_report["software_checks_passed"]
            and captures_passed
        ),
        "domain_verified": False,
        "procedure_verified": False,
        "method_verified": False,
        "artifact_authenticity_verified": False,
        "physical_qualification_passed": False,
        "human_review_status": "unverified",
    }
