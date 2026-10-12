"""Check pinned qualification vectors using only an isolated installed distribution.

Run with the consumer venv's Python -I, outside the checkout, and pass the corpus
paths. The corpora supply bytes and expected results, never executable helpers.
"""

import hashlib
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import aethron
import qualification
from qualification.artifacts import verify
from qualification.assessment import evaluate
from qualification.campaign_bundle import evaluate as evaluate_bundle

CORPUS_SHA256 = "afe52af644bbc67dc0bdb0df3d13839ab1a3c3d768471ce32b02d314d899fa2c"
CASE_IDS = {
    "complete",
    "stale",
    "domain_unknown",
    "method_unknown",
    "artifact_missing",
    "simultaneous",
    "reused",
    "malformed_capture",
    "invalid_plan",
    "invalid_instant",
}
BUNDLE_CORPUS_SHA256 = "8c3f345a6e8e3b947ca94ca4b4e0817e2d3961ff43bade6cff2adc5f2b4daff9"
BUNDLE_CASE_IDS = {
    "complete",
    "stale",
    "altered_artifact",
    "wrong_references",
    "expired_and_altered",
    "reused_capture",
}


def corpus(path):
    with path.open("rb") as stream:
        raw = stream.read(262145)
    if hashlib.sha256(raw).hexdigest() != CORPUS_SHA256:
        raise ValueError("assessment_corpus_mismatch")
    cases = json.loads(raw)["cases"]
    if len(cases) != 10 or {case["id"] for case in cases} != CASE_IDS:
        raise ValueError("assessment_case_mismatch")
    return cases


def arguments(case):
    return (
        bytes.fromhex(case["plan_hex"]),
        [
            {
                "case_id": row["case_id"],
                "now_ms": row["now_ms"],
                "manifest": bytes.fromhex(row["manifest_hex"]),
                "artifacts": {key: bytes.fromhex(raw) for key, raw in row["artifacts_hex"].items()},
            }
            for row in case["captures"]
        ],
        bytes.fromhex(case["domain_hex"]),
        bytes.fromhex(case["procedure_hex"]),
        {key: bytes.fromhex(raw) for key, raw in case["methods_hex"].items()},
    )


def _blob(raw):
    return struct.pack(">I", len(raw)) + raw


def _byte_map(entries):
    return struct.pack(">I", len(entries)) + b"".join(
        key.encode("ascii") + _blob(raw) for key, raw in entries.items()
    )


def frame(args):
    plan, captures, domain, procedure, methods = args
    parts = [b"AETHRON-QUALIFICATION-ASSESSMENT-V1\n"]
    parts.extend(_blob(raw) for raw in (plan, domain, procedure))
    parts.extend((_byte_map(methods), struct.pack(">I", len(captures))))
    for row in captures:
        parts.extend(
            (
                _blob(row["case_id"].encode("ascii")),
                _blob(json.dumps(row["now_ms"]).encode("ascii")),
                _blob(row["manifest"]),
                _byte_map(row["artifacts"]),
            )
        )
    return b"".join(parts)


def canonical(value):
    # Serialized comparison distinguishes booleans, integers and floats.
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def check_case(case):
    args = arguments(case)
    error = case["expected_error"]
    if error is not None:
        try:
            evaluate(*args)
        except ValueError as exc:
            if str(exc) != error:
                raise AssertionError("assessment_error_mismatch") from exc
        else:
            raise AssertionError("assessment_error_missing")
        expected = (2, b"", (error + os.linesep).encode("ascii"))
    else:
        report = evaluate(*args)
        if canonical(report) != canonical(case["expected_report"]):
            raise AssertionError("assessment_report_mismatch")
        expected = (
            0 if case["id"] == "complete" else 1,
            (canonical(case["expected_report"]) + os.linesep).encode("ascii"),
            b"",
        )
    result = subprocess.run(
        [sys.executable, "-I", "-m", "qualification.assessment_cli"],
        input=frame(args),
        capture_output=True,
        check=False,
        timeout=10,
    )
    if (result.returncode, result.stdout, result.stderr) != expected:
        raise AssertionError("assessment_process_mismatch")


def bundle_corpus(path):
    with path.open("rb") as stream:
        raw = stream.read(32769)
    if hashlib.sha256(raw).hexdigest() != BUNDLE_CORPUS_SHA256:
        raise ValueError("bundle_corpus_mismatch")
    data = json.loads(raw)
    cases = data["cases"]
    if len(cases) != 6 or {case["id"] for case in cases} != BUNDLE_CASE_IDS:
        raise ValueError("bundle_case_mismatch")
    return data


def bundle_arguments(data, case):
    return (
        data["plan_utf8"].encode("utf-8"),
        [
            {
                "case_id": row["case_id"],
                "now_ms": row["now_ms"],
                "manifest": data["manifests_utf8"][row["manifest_key"]].encode("utf-8"),
            }
            for row in case["captures"]
        ],
        bytes.fromhex(case["domain_hex"]),
        bytes.fromhex(case["procedure_hex"]),
    )


def bundle_frame(args):
    plan, captures, domain, procedure = args
    parts = [b"AETHRON-QUALIFICATION-BUNDLE-V1\n"]
    parts.extend(_blob(raw) for raw in (plan, domain, procedure))
    parts.append(struct.pack(">I", len(captures)))
    for row in captures:
        parts.extend(
            (
                _blob(row["case_id"].encode("ascii")),
                struct.pack(">Q", row["now_ms"]),
                _blob(row["manifest"]),
            )
        )
    return b"".join(parts)


def check_bundle_case(data, case):
    args = bundle_arguments(data, case)
    report = evaluate_bundle(*args)
    projection = {
        "coverage_findings": report["coverage"]["findings"],
        "reference_findings": report["references"]["reference_findings"],
        "software_checks_passed": report["software_checks_passed"],
        "capture_counts": report["coverage"]["capture_counts"],
    }
    if canonical(projection) != canonical(case["expected"]["bundle"]):
        raise AssertionError("bundle_report_mismatch")
    for key in (
        "artifact_bytes_verified",
        "artifact_authenticity_verified",
        "domain_verified",
        "procedure_verified",
        "physical_qualification_passed",
    ):
        if report[key] is not False:
            raise AssertionError("bundle_qualification_claim")
    for nested in (report, report["coverage"], report["references"]):
        if nested["plan_sha256"] != hashlib.sha256(args[0]).hexdigest():
            raise AssertionError("bundle_plan_mismatch")
        if nested["physical_qualification_passed"] is not False:
            raise AssertionError("bundle_qualification_claim")
    supplied = {key: bytes.fromhex(raw) for key, raw in case["artifacts_hex"].items()}
    if len(args[1]) != len(case["expected"]["artifacts"]):
        raise AssertionError("bundle_artifact_inventory_mismatch")
    for row, expected in zip(args[1], case["expected"]["artifacts"]):
        artifact = verify(row["manifest"], supplied, now_ms=row["now_ms"])
        projection = {
            "declaration_findings": artifact["declaration"]["findings"],
            "artifact_findings": artifact["artifact_findings"],
            "software_checks_passed": artifact["software_checks_passed"],
            "artifact_bytes_verified": artifact["artifact_bytes_verified"],
        }
        if canonical(projection) != canonical(expected):
            raise AssertionError("bundle_artifact_mismatch")
        if artifact["declaration"]["input_sha256"] != hashlib.sha256(row["manifest"]).hexdigest():
            raise AssertionError("bundle_manifest_mismatch")
        for key in ("artifact_authenticity_verified", "physical_qualification_passed"):
            if artifact[key] is not False:
                raise AssertionError("bundle_artifact_claim")
    result = subprocess.run(
        [sys.executable, "-I", "-m", "qualification.campaign_bundle_cli"],
        input=bundle_frame(args),
        capture_output=True,
        check=False,
        timeout=10,
    )
    # The corpus pins projections; require the process to match the full library
    # report byte-for-byte too, without claiming a full independent report oracle.
    expected = (
        0 if case["expected"]["bundle"]["software_checks_passed"] else 1,
        (canonical(report) + os.linesep).encode("ascii"),
        b"",
    )
    if (result.returncode, result.stdout, result.stderr) != expected:
        raise AssertionError("bundle_process_mismatch")


def main():
    if not sys.flags.isolated or sys.prefix == sys.base_prefix:
        raise RuntimeError("isolated_consumer_venv_required")
    for module in (aethron, qualification):
        # Do not resolve sys.executable: POSIX venvs can symlink the base binary.
        if Path(sys.prefix).resolve() not in Path(module.__file__).resolve().parents:
            raise RuntimeError("installed_module_required")
    for case in corpus(Path(sys.argv[1])):
        check_case(case)
    data = bundle_corpus(Path(sys.argv[2]))
    for case in data["cases"]:
        check_bundle_case(data, case)
    print(
        json.dumps(
            {
                "assessment_vectors": 10,
                "bundle_vectors": 6,
                "artifact_vectors": 7,
                "isolated_install": True,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
