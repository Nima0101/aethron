"""Check pinned qualification vectors using only an isolated installed distribution.

Run with the consumer venv's Python -I, outside the checkout, and pass the corpus
paths. The corpora supply bytes and expected results, never executable helpers.
"""

import copy
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


def check_opaque_artifacts(case):
    args = arguments(case)
    artifacts = args[1][0]["artifacts"]
    # Match the source binary-process contract: Windows text input would
    # translate CRLF and stop at Ctrl-Z; the artifact must remain opaque.
    for digest in artifacts:
        artifacts[digest] += b"\r\n\x1a\x00\xffPRIVATE"
    expected_report = copy.deepcopy(case["expected_report"])
    expected_report["submission_sha256"] = (
        "fbea20aaff18a378bb6aec803d1079948913f19e19d3f4ecb5b0ebb8082f4d25"
    )
    artifact = expected_report["captures"][0]["report"]
    artifact["artifact_counts"].update(matched=0, mismatched=1, supplied_bytes=15)
    artifact["artifact_findings"] = ["artifact_digest_mismatch"]
    for report in (artifact, expected_report):
        report["artifact_bytes_verified"] = False
        report["software_checks_passed"] = False
    # Everything else remains pinned to the complete vector, including every
    # false qualification flag. The new commitment binds the exact opaque bytes.
    if canonical(evaluate(*args)) != canonical(expected_report):
        raise AssertionError("opaque_assessment_report_mismatch")
    result = subprocess.run(
        [sys.executable, "-I", "-m", "qualification.assessment_cli"],
        input=frame(args),
        capture_output=True,
        check=False,
        timeout=10,
    )
    expected = (1, (canonical(expected_report) + os.linesep).encode("ascii"), b"")
    if (result.returncode, result.stdout, result.stderr) != expected:
        raise AssertionError("opaque_assessment_process_mismatch")


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


def malformed_frames(raw, magic, oversized):
    # Representative truncations cover magic, a partial length and the final
    # payload. Source tests exhaust every byte offset and pre-read bound.
    cases = {
        "empty": b"",
        "truncated_magic": magic[:-1],
        "truncated_length": raw[: len(magic) + 3],
        "truncated_payload": raw[:-1],
        "trailing_bytes": raw + b"\r\n\x1a\x00\xffPRIVATE",
        "second_frame": raw + raw,
    }
    cases.update(("oversized_" + name, header) for name, header in oversized.items())
    return cases


def assessment_malformed_frames(args):
    plan, rows, domain, procedure, methods = args
    magic = b"AETHRON-QUALIFICATION-ASSESSMENT-V1\n"
    docs = magic + _blob(plan) + _blob(domain) + _blob(procedure)
    mapped = docs + _byte_map(methods)
    row = rows[0]
    capture = mapped + struct.pack(">I", 1) + _blob(row["case_id"].encode("ascii"))
    instant = _blob(json.dumps(row["now_ms"]).encode("ascii"))
    manifest = capture + instant + _blob(row["manifest"])
    # Frozen v1 bounds, independently pinned rather than imported from the CLI.
    oversized = {
        "plan": magic + struct.pack(">I", 65537),
        "domain": magic + _blob(plan) + struct.pack(">I", 65537),
        "procedure": magic + _blob(plan) + _blob(domain) + struct.pack(">I", 65537),
        "method_count": docs + struct.pack(">I", 49),
        "method": docs + struct.pack(">I", 1) + b"a" * 64 + struct.pack(">I", 65537),
        "capture_count": mapped + struct.pack(">I", 65),
        "case_id": mapped + struct.pack(">II", 1, 65),
        "instant": capture + struct.pack(">I", 18),
        "manifest": capture + instant + struct.pack(">I", 65537),
        "artifact_count": manifest + struct.pack(">I", 16),
        "artifact": manifest + struct.pack(">I", 1) + b"a" * 64 + struct.pack(">I", 1048577),
    }
    cases = malformed_frames(frame(args), magic, oversized)
    capture_fields = _blob(row["case_id"].encode("ascii")) + instant + _blob(row["manifest"])
    # Include complete envelopes as well as headers: rejection must not pass
    # solely because a missing value or trailing capture count reaches EOF.
    for kind, prefix, suffix in (
        ("method", docs, struct.pack(">I", 1) + capture_fields + _byte_map(row["artifacts"])),
        ("artifact", mapped + struct.pack(">I", 1) + capture_fields, b""),
    ):
        for name, key in (
            ("uppercase", b"A" * 64),
            ("non_ascii", b"\xff" * 64),
            ("non_hex", b"g" * 64),
        ):
            header = prefix + struct.pack(">I", 1) + key
            cases[kind + "_" + name + "_key_header"] = header
            cases[kind + "_" + name + "_key_frame"] = header + _blob(b"PRIVATE") + suffix
        header = prefix + struct.pack(">I", 2) + b"a" * 64 + _blob(b"abc") + b"a" * 64
        cases[kind + "_duplicate_key_header"] = header
        cases[kind + "_duplicate_key_frame"] = header + _blob(b"PRIVATE") + suffix
    # Complete envelopes isolate scalar validation from truncation/length
    # rejection. Pin the wire tokens so bool/float/string coercion cannot pass.
    for name, token in (
        ("true", b"true"),
        ("false", b"false"),
        ("float", b"1050.0"),
        ("string", b'"1050"'),
        ("null", b"null"),
        ("array", b"[]"),
        ("object", b"{}"),
        ("negative", b"-1"),
        ("above_maximum", b"9007199254739993"),
        ("overflow", b"9007199254740992"),
        ("infinity", b"Infinity"),
    ):
        cases["instant_" + name + "_frame"] = (
            capture + _blob(token) + _blob(row["manifest"]) + _byte_map(row["artifacts"])
        )
    for name, token in (("empty", b""), ("space", b"PRIVATE name"), ("path", b"a/b")):
        cases["case_id_" + name + "_frame"] = (
            mapped
            + struct.pack(">I", 1)
            + _blob(token)
            + instant
            + _blob(row["manifest"])
            + _byte_map(row["artifacts"])
        )
    return cases


def bundle_malformed_frames(args):
    plan, rows, domain, procedure = args
    magic = b"AETHRON-QUALIFICATION-BUNDLE-V1\n"
    docs = magic + _blob(plan) + _blob(domain) + _blob(procedure)
    row = rows[0]
    capture = docs + struct.pack(">I", 1) + _blob(row["case_id"].encode("ascii"))
    oversized = {
        "plan": magic + struct.pack(">I", 65537),
        "domain": magic + _blob(plan) + struct.pack(">I", 1048577),
        "procedure": magic + _blob(plan) + _blob(domain) + struct.pack(">I", 1048577),
        "capture_count": docs + struct.pack(">I", 65),
        "case_id": docs + struct.pack(">II", 1, 65),
        "manifest": capture + struct.pack(">QI", row["now_ms"], 65537),
        "uint32": magic + b"\xff" * 4,
    }
    return malformed_frames(bundle_frame(args), magic, oversized)


def check_malformed_frames(module, cases, diagnostic):
    expected = (2, b"", (diagnostic + os.linesep).encode("ascii"))
    for name, raw in cases.items():
        result = subprocess.run(
            [sys.executable, "-I", "-m", module],
            input=raw,
            capture_output=True,
            check=False,
            timeout=10,
        )
        if (result.returncode, result.stdout, result.stderr) != expected:
            raise AssertionError("malformed_process_mismatch:" + module + ":" + name)
    return len(cases)


def main():
    if not sys.flags.isolated or sys.prefix == sys.base_prefix:
        raise RuntimeError("isolated_consumer_venv_required")
    for module in (aethron, qualification):
        # Do not resolve sys.executable: POSIX venvs can symlink the base binary.
        if Path(sys.prefix).resolve() not in Path(module.__file__).resolve().parents:
            raise RuntimeError("installed_module_required")
    cases = corpus(Path(sys.argv[1]))
    for case in cases:
        check_case(case)
    data = bundle_corpus(Path(sys.argv[2]))
    for case in data["cases"]:
        check_bundle_case(data, case)
    complete = next(case for case in cases if case["id"] == "complete")
    check_opaque_artifacts(complete)
    assessment_malformed = check_malformed_frames(
        "qualification.assessment_cli",
        assessment_malformed_frames(arguments(complete)),
        "invalid_qualification_assessment",
    )
    complete_bundle = next(case for case in data["cases"] if case["id"] == "complete")
    bundle_malformed = check_malformed_frames(
        "qualification.campaign_bundle_cli",
        bundle_malformed_frames(bundle_arguments(data, complete_bundle)),
        "invalid_campaign_bundle",
    )
    print(
        json.dumps(
            {
                "assessment_vectors": 10,
                "bundle_vectors": 6,
                "artifact_vectors": 7,
                "assessment_opaque_artifact_cases": 1,
                "assessment_malformed_frames": assessment_malformed,
                "bundle_malformed_frames": bundle_malformed,
                "isolated_install": True,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
