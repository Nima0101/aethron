"""Check pinned qualification vectors using only an isolated installed distribution.

Run with the consumer venv's Python -I, outside the checkout, and pass the corpus
paths. The corpora supply bytes and expected results, never executable helpers.
"""

import contextlib
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
from qualification.evidence import validate

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


def check_declaration(case):
    row = case["captures"][0]
    raw = bytes.fromhex(row["manifest_hex"])
    # Reuse the independently pinned declaration, including typed counts,
    # retained stale findings and false artifact/physical qualification flags.
    expected_report = case["expected_report"]["captures"][0]["report"]["declaration"]
    if canonical(validate(raw, now_ms=row["now_ms"])) != canonical(expected_report):
        raise AssertionError("declaration_report_mismatch")
    expected = (
        0 if case["id"] == "complete" else 1,
        (canonical(expected_report) + os.linesep).encode("ascii"),
        b"",
    )
    instant = str(row["now_ms"])
    for args in (["--now-ms", instant], ["--now-ms=" + instant]):
        result = subprocess.run(
            [sys.executable, "-I", "-m", "qualification", *args],
            input=raw,
            capture_output=True,
            check=False,
            timeout=10,
        )
        if (result.returncode, result.stdout, result.stderr) != expected:
            raise AssertionError("declaration_process_mismatch")
    return 2


def invalid_declaration_arguments():
    # Help is supported by this CLI. Only ambiguous, missing, invalid or
    # unexpected arguments belong in these rejection cases.
    cases = {
        "repeated_separate": ["--now-ms", "1151", "--now-ms", "1050"],
        "repeated_equals": ["--now-ms=1050", "--now-ms=1151"],
        "mixed_equal_instants": ["--now-ms", "1050", "--now-ms=1050"],
        "mixed_stale_override": ["--now-ms=1151", "--now-ms", "1050"],
        "missing_option": [],
        "missing_value": ["--now-ms"],
        "empty_value": ["--now-ms="],
    }
    for option in ("--now", "--now-m", "--n"):
        cases["abbreviated_separate:" + option] = [option, "1050"]
        cases["abbreviated_equals:" + option] = [option + "=1050"]
    for name, value in (
        ("text", "PRIVATE instant with spaces"),
        ("fraction", "1.5"),
        ("nonfinite", "NaN"),
        ("boolean", "True"),
        ("negative", "-1"),
        ("over_maximum", "9007199254739993"),
    ):
        cases[name + ":separate"] = ["--now-ms", value]
        cases[name + ":equals"] = ["--now-ms=" + value]
    for name, extra in (
        ("positional", ["PRIVATE path with spaces"]),
        ("empty_positional", [""]),
        ("after_separator", ["--", "PRIVATE"]),
        ("unknown_option", ["--PRIVATE"]),
    ):
        cases[name] = ["--now-ms", "1050", *extra]
    return cases


def check_declaration_arguments(case):
    # The same complete manifest passes at 1050 and is stale at 1151 in
    # check_declaration; neither malformed stdin nor missing time masks argv.
    raw = bytes.fromhex(case["captures"][0]["manifest_hex"])
    cases = invalid_declaration_arguments()
    expected = (2, b"", ("invalid_qualification_manifest" + os.linesep).encode("ascii"))
    for name, args in cases.items():
        result = subprocess.run(
            [sys.executable, "-I", "-m", "qualification", *args],
            input=raw,
            capture_output=True,
            check=False,
            timeout=10,
        )
        if (result.returncode, result.stdout, result.stderr) != expected:
            raise AssertionError("declaration_argument_process_mismatch:" + name)
    return len(cases)


def declaration_malformed_inputs(raw):
    return {
        "one_byte_over": raw.ljust(65537, b" "),
        "trailing_non_whitespace": raw + b"PRIVATE",
        "concatenated_json": raw + raw,
        "truncated_json": raw.rstrip()[:-1],
        "invalid_utf8": b"\xff" + raw,
    }


def check_declaration_input_boundary(case):
    row = case["captures"][0]
    raw = bytes.fromhex(row["manifest_hex"]).ljust(65536, b" ")
    expected_report = copy.deepcopy(case["expected_report"]["captures"][0]["report"]["declaration"])
    # Whitespace changes the byte commitment, but no typed semantic finding.
    expected_report["input_sha256"] = hashlib.sha256(raw).hexdigest()
    if canonical(validate(raw, now_ms=row["now_ms"])) != canonical(expected_report):
        raise AssertionError("declaration_boundary_report_mismatch")
    result = subprocess.run(
        [sys.executable, "-I", "-m", "qualification", "--now-ms", str(row["now_ms"])],
        input=raw,
        capture_output=True,
        check=False,
        timeout=10,
    )
    expected = (0, (canonical(expected_report) + os.linesep).encode("ascii"), b"")
    if (result.returncode, result.stdout, result.stderr) != expected:
        raise AssertionError("declaration_boundary_process_mismatch")
    return 1


def check_declaration_malformed_inputs(case):
    row = case["captures"][0]
    cases = declaration_malformed_inputs(bytes.fromhex(row["manifest_hex"]))
    expected = (2, b"", ("invalid_qualification_manifest" + os.linesep).encode("ascii"))
    for name, raw in cases.items():
        result = subprocess.run(
            [sys.executable, "-I", "-m", "qualification", "--now-ms", str(row["now_ms"])],
            input=raw,
            capture_output=True,
            check=False,
            timeout=10,
        )
        if (result.returncode, result.stdout, result.stderr) != expected:
            raise AssertionError("declaration_input_process_mismatch:" + name)
    return len(cases)


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


def aggregate_artifact_arguments(args):
    # Pin the frozen 4 MiB aggregate independently of the runtime constants.
    # Repeated keys/payloads in different captures still consume the allowance.
    cases = {}
    for name, groups in (
        ("single_capture", (4,)),
        ("across_captures", (1, 1, 1, 1)),
    ):
        plan, rows, domain, procedure, methods = copy.deepcopy(args)
        template = rows[0]
        rows = [
            dict(template, artifacts={f"{i:064x}": b"x" * 1048576 for i in range(count)})
            for count in groups
        ]
        # Empty payloads remain admissible when the byte allowance is exhausted.
        rows.append(dict(template, artifacts={"0" * 64: b""}))
        cases[name] = (plan, rows, domain, procedure, methods)
    return cases


def check_aggregate_artifacts(case):
    for name, args in aggregate_artifact_arguments(arguments(case)).items():
        report = evaluate(*args)
        expected_counts = (4, 0) if name == "single_capture" else (1, 1, 1, 1, 0)
        projection = [
            {
                "counts": row["report"]["artifact_counts"],
                "findings": row["report"]["artifact_findings"],
            }
            for row in report["captures"]
        ]
        expected = [
            {
                "counts": {
                    "referenced": 1,
                    "supplied": count or 1,
                    "matched": 0,
                    "missing": 1,
                    "mismatched": 0,
                    "unreferenced": count or 1,
                    "supplied_bytes": count * 1048576,
                },
                "findings": ["artifact_missing", "artifact_unreferenced"],
            }
            for count in expected_counts
        ]
        if canonical(projection) != canonical(expected):
            raise AssertionError("aggregate_assessment_report_mismatch:" + name)
        for nested in (report, *(row["report"] for row in report["captures"])):
            for key in (
                "artifact_bytes_verified",
                "software_checks_passed",
                "artifact_authenticity_verified",
                "physical_qualification_passed",
            ):
                if nested[key] is not False:
                    raise AssertionError("aggregate_assessment_claim:" + name)
        result = subprocess.run(
            [sys.executable, "-I", "-m", "qualification.assessment_cli"],
            input=frame(args),
            capture_output=True,
            check=False,
            timeout=10,
        )
        # Independently pinned counts/findings above plus full library/CLI parity.
        expected_process = (1, (canonical(report) + os.linesep).encode("ascii"), b"")
        if (result.returncode, result.stdout, result.stderr) != expected_process:
            raise AssertionError("aggregate_assessment_process_mismatch:" + name)
    return 2


def exact_limit_arguments(args):
    # Independent frozen wire limits; invalid opaque content is admitted as
    # negative evidence, never mistaken for an invalid envelope.
    plan, rows, domain, procedure, _ = copy.deepcopy(args)
    methods = {f"{i:064x}": b"\xff" * 65536 for i in range(48)}
    row = rows[0]
    row["case_id"] = "a" * 64
    row["manifest"] = row["manifest"].ljust(65536, b" ")
    row["artifacts"] = {f"{i:064x}": b"\xff" * 1048576 for i in range(4)}
    row["artifacts"].update((f"{i:064x}", b"") for i in range(4, 15))
    rows = [row, *(dict(row, artifacts={}) for _ in range(63))]
    return (
        plan.ljust(65536, b" "),
        rows,
        domain.ljust(65536, b" "),
        procedure.ljust(65536, b" "),
        methods,
    )


def check_exact_limits(case):
    args = exact_limit_arguments(arguments(case))
    report = evaluate(*args)
    projection = {
        "capture_counts": report["coverage"]["capture_counts"],
        "coverage_findings": report["coverage"]["findings"],
        "domain_findings": report["domain"]["findings"],
        "procedure_findings": report["methods"]["procedure"]["findings"],
        "method_counts": report["methods"]["method_counts"],
        "method_findings": report["methods"]["method_findings"],
        "captures": [
            {
                "index": row["capture_index"],
                "findings": row["findings"],
                "counts": row["report"]["artifact_counts"],
                "artifact_findings": row["report"]["artifact_findings"],
                "manifest_sha256": row["report"]["declaration"]["input_sha256"],
            }
            for row in report["captures"]
        ],
    }
    expected = {
        "capture_counts": {"submitted": 64, "eligible": 0, "rejected": 64},
        "coverage_findings": ["capture_coverage_missing", "capture_reused", "capture_unplanned"],
        "domain_findings": ["domain_digest_mismatch"],
        "procedure_findings": ["procedure_digest_mismatch"],
        "method_counts": {"referenced": 3, "supplied": 48, "supplied_bytes": 3145728},
        "method_findings": [
            "method_digest_mismatch",
            "method_invalid",
            "method_missing",
            "method_unreferenced",
        ],
        "captures": [
            {
                "index": i,
                "findings": [],
                "counts": {
                    "referenced": 1,
                    "supplied": 15 if i == 0 else 0,
                    "matched": 0,
                    "missing": 1,
                    "mismatched": 0,
                    "unreferenced": 15 if i == 0 else 0,
                    "supplied_bytes": 4194304 if i == 0 else 0,
                },
                "artifact_findings": (
                    ["artifact_missing", "artifact_unreferenced"]
                    if i == 0
                    else ["artifact_missing"]
                ),
                "manifest_sha256": hashlib.sha256(args[1][i]["manifest"]).hexdigest(),
            }
            for i in range(64)
        ],
    }
    if canonical(projection) != canonical(expected):
        raise AssertionError("exact_limit_assessment_report_mismatch")
    # Check each layer's negative/authority flags, including numeric impostors.
    template = case["expected_report"]
    artifact_template = template["captures"][0]["report"]
    for nested, baseline in (
        (report, template),
        (report["coverage"], template["coverage"]),
        (report["domain"], template["domain"]),
        (report["methods"], template["methods"]),
        (report["methods"]["procedure"], template["methods"]["procedure"]),
        *((row["report"], artifact_template) for row in report["captures"]),
        *(
            (row["report"]["declaration"], artifact_template["declaration"])
            for row in report["captures"]
        ),
    ):
        for key in baseline:
            if key.endswith("_verified") or key in (
                "software_checks_passed",
                "physical_qualification_passed",
                "declaration_coverage_complete",
                "domain_declaration_checks_passed",
                "procedure_declaration_checks_passed",
            ):
                if nested.get(key) is not False:
                    raise AssertionError("exact_limit_assessment_claim")
    result = subprocess.run(
        [sys.executable, "-I", "-m", "qualification.assessment_cli"],
        input=frame(args),
        capture_output=True,
        check=False,
        timeout=10,
    )
    expected_process = (1, (canonical(report) + os.linesep).encode("ascii"), b"")
    if (result.returncode, result.stdout, result.stderr) != expected_process:
        raise AssertionError("exact_limit_assessment_process_mismatch")
    return 1


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


def bundle_exact_limit_arguments(args):
    # Bundle references are opaque 1 MiB payloads, unlike assessment documents.
    plan, rows, _domain, _procedure = copy.deepcopy(args)
    row = dict(rows[0], case_id="a" * 64, manifest=rows[0]["manifest"].ljust(65536, b" "))
    return (
        plan.ljust(65536, b" "),
        [dict(row) for _ in range(64)],
        b"\xff" * 1048576,
        b"\0" * 1048576,
    )


def check_bundle_exact_limits(data, case):
    args = bundle_exact_limit_arguments(bundle_arguments(data, case))
    report = evaluate_bundle(*args)
    plan_digest = hashlib.sha256(args[0]).hexdigest()
    bindings = [
        [row["case_id"], hashlib.sha256(row["manifest"]).hexdigest(), row["now_ms"]]
        for row in args[1]
    ]
    capture_digest = hashlib.sha256(
        b"aethron.qualification.captures.v1\0" + canonical(bindings).encode("ascii")
    ).hexdigest()
    common = {
        "version": 1,
        "plan_sha256": plan_digest,
        "domain_verified": False,
        "procedure_verified": False,
        "artifact_authenticity_verified": False,
        "physical_qualification_passed": False,
    }
    expected_report = dict(
        common,
        artifact_bytes_verified=False,
        software_checks_passed=False,
        coverage=dict(
            common,
            captures_sha256=capture_digest,
            capture_counts={"submitted": 64, "eligible": 0, "rejected": 64},
            cases=[{"case_index": 0, "required": 1, "eligible": 0}],
            findings=["capture_coverage_missing", "capture_reused", "capture_unplanned"],
            declaration_coverage_complete=False,
        ),
        references=dict(
            common,
            reference_counts={"supplied": 2, "matched": 0, "supplied_bytes": 2097152},
            reference_findings=["domain_digest_mismatch", "procedure_digest_mismatch"],
            reference_bytes_verified=False,
        ),
    )
    if canonical(report) != canonical(expected_report):
        raise AssertionError("exact_limit_bundle_report_mismatch")
    result = subprocess.run(
        [sys.executable, "-I", "-m", "qualification.campaign_bundle_cli"],
        input=bundle_frame(args),
        capture_output=True,
        check=False,
        timeout=10,
    )
    expected = (1, (canonical(expected_report) + os.linesep).encode("ascii"), b"")
    if (result.returncode, result.stdout, result.stderr) != expected:
        raise AssertionError("exact_limit_bundle_process_mismatch")
    return 1


def check_bundle_scalar_boundaries(data, case):
    for instant, finding in (
        (0, "declaration_capture_future"),
        (9007199254739992, "declaration_capture_stale"),
    ):
        args = bundle_arguments(data, case)
        args[1][0]["now_ms"] = instant
        row = args[1][0]
        bindings = [[row["case_id"], hashlib.sha256(row["manifest"]).hexdigest(), instant]]
        common = {
            "version": 1,
            "plan_sha256": hashlib.sha256(args[0]).hexdigest(),
            "domain_verified": False,
            "procedure_verified": False,
            "artifact_authenticity_verified": False,
            "physical_qualification_passed": False,
        }
        expected = dict(
            common,
            artifact_bytes_verified=False,
            software_checks_passed=False,
            coverage=dict(
                common,
                captures_sha256=hashlib.sha256(
                    b"aethron.qualification.captures.v1\0" + canonical(bindings).encode("ascii")
                ).hexdigest(),
                capture_counts={"submitted": 1, "eligible": 0, "rejected": 1},
                cases=[{"case_index": 0, "required": 1, "eligible": 0}],
                findings=["capture_coverage_missing", finding],
                declaration_coverage_complete=False,
            ),
            references=dict(
                common,
                reference_counts={"supplied": 2, "matched": 2, "supplied_bytes": 6},
                reference_findings=[],
                reference_bytes_verified=True,
            ),
        )
        if canonical(evaluate_bundle(*args)) != canonical(expected):
            raise AssertionError("scalar_boundary_bundle_report_mismatch")
        result = subprocess.run(
            [sys.executable, "-I", "-m", "qualification.campaign_bundle_cli"],
            input=bundle_frame(args),
            capture_output=True,
            check=False,
            timeout=10,
        )
        if (result.returncode, result.stdout, result.stderr) != (
            1,
            (canonical(expected) + os.linesep).encode("ascii"),
            b"",
        ):
            raise AssertionError("scalar_boundary_bundle_process_mismatch")
    return 2


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
    # Complete one-over envelopes isolate each resource bound from EOF and
    # aggregate overflow. Keep the remaining fields valid and independently
    # exercise count limits with small payloads.
    for name in (
        "plan",
        "domain",
        "procedure",
        "manifest",
        "method_count",
        "method",
        "capture_count",
        "artifact_count",
        "artifact",
    ):
        enlarged = list(copy.deepcopy(args))
        if name in ("plan", "domain", "procedure"):
            index = {"plan": 0, "domain": 2, "procedure": 3}[name]
            enlarged[index] += b" " * (65537 - len(enlarged[index]))
        elif name == "manifest":
            raw = enlarged[1][0]["manifest"]
            enlarged[1][0]["manifest"] = raw + b" " * (65537 - len(raw))
        elif name == "method_count":
            enlarged[4] = {f"{i:064x}": b"" for i in range(49)}
        elif name == "method":
            enlarged[4] = {"a" * 64: b"\xff" * 65537}
        elif name == "capture_count":
            enlarged[1] = [copy.deepcopy(rows[0]) for _ in range(65)]
        elif name == "artifact_count":
            enlarged[1][0]["artifacts"] = {f"{i:064x}": b"" for i in range(16)}
        else:
            enlarged[1][0]["artifacts"] = {"a" * 64: b"\xff" * 1048577}
        cases["oversized_" + name + "_frame"] = frame(enlarged)
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
    for name, boundary in aggregate_artifact_arguments(args).items():
        boundary[1][-1]["artifacts"]["0" * 64] = b"x"
        cases["aggregate_" + name + "_frame"] = frame(boundary)
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
    cases = malformed_frames(bundle_frame(args), magic, oversized)
    # Complete frames distinguish bound rejection from a missing payload/EOF.
    for name in ("plan", "domain", "procedure", "manifest", "capture_count", "case_id"):
        enlarged = list(copy.deepcopy(args))
        if name in ("plan", "domain", "procedure"):
            index = {"plan": 0, "domain": 2, "procedure": 3}[name]
            limit = 65536 if name == "plan" else 1048576
            enlarged[index] = enlarged[index].ljust(limit + 1, b" ")
        elif name == "manifest":
            enlarged[1][0]["manifest"] = row["manifest"].ljust(65537, b" ")
        elif name == "capture_count":
            enlarged[1] = [dict(row) for _ in range(65)]
        else:
            enlarged[1][0]["case_id"] = "a" * 65
        cases["oversized_" + name + "_frame"] = bundle_frame(enlarged)
    # Binary uint64 instants have no JSON types/coercions. Exercise both the
    # semantic maximum and the wire maximum with every later field present.
    for name, instant in (("above_maximum", 9007199254739993), ("uint64_maximum", 2**64 - 1)):
        cases["instant_" + name + "_frame"] = (
            capture + struct.pack(">Q", instant) + _blob(row["manifest"])
        )
    for name, token in (
        ("empty", b""),
        ("space", b"PRIVATE name"),
        ("path", b"a/b"),
        ("non_ascii", b"\xff"),
    ):
        cases["case_id_" + name + "_frame"] = (
            docs
            + struct.pack(">I", 1)
            + _blob(token)
            + struct.pack(">Q", row["now_ms"])
            + _blob(row["manifest"])
        )
    return cases


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


def unexpected_arguments():
    return {
        "long_option": ["--PRIVATE"],
        "long_help": ["--help"],
        "short_help": ["-h"],
        "positional": ["PRIVATE"],
        "empty": [""],
        "separator": ["--"],
        "option_value": ["--input", "PRIVATE path with spaces"],
        "after_separator": ["--", "PRIVATE"],
    }


def check_unexpected_arguments(module, raw, diagnostic):
    # The complete frame already passes without arguments in the vector checks.
    # Rejection must therefore be attributable to argv, not malformed stdin.
    cases = unexpected_arguments()
    expected = (2, b"", (diagnostic + os.linesep).encode("ascii"))
    for name, args in cases.items():
        result = subprocess.run(
            [sys.executable, "-I", "-m", module, *args],
            input=raw,
            capture_output=True,
            check=False,
            timeout=10,
        )
        if (result.returncode, result.stdout, result.stderr) != expected:
            raise AssertionError("argument_process_mismatch:" + module + ":" + name)
    return len(cases)


def closed_pipe_frames(cases, encode):
    selected = {
        name: encode(next(case for case in cases if case["id"] == name))
        for name in ("complete", "stale")
    }
    return dict(selected, malformed=b"PRIVATE malformed")


def declaration_closed_pipe_inputs(cases):
    selected = {
        name: next(case for case in cases if case["id"] == name)["captures"][0]
        for name in ("complete", "stale")
    }
    frames = {name: bytes.fromhex(row["manifest_hex"]) for name, row in selected.items()}
    arguments = {name: ["--now-ms", str(row["now_ms"])] for name, row in selected.items()}
    frames["malformed"] = b"PRIVATE malformed"
    arguments["malformed"] = list(arguments["complete"])
    return frames, arguments


def check_closed_pipes(module, cases, diagnostic, *, case_arguments=None):
    checked = 0
    for name, raw in cases.items():
        args = () if case_arguments is None else case_arguments[name]
        for close_errors in (False, True):
            with contextlib.ExitStack() as stack:
                read_fd, write_fd = os.pipe()
                os.close(read_fd)
                # Remove readers before spawning: a deterministic broken pipe,
                # including on Windows, without sleeps or shell pipelines.
                output = stack.enter_context(os.fdopen(write_fd, "wb"))
                errors = subprocess.PIPE
                if close_errors:
                    read_fd, write_fd = os.pipe()
                    os.close(read_fd)
                    errors = stack.enter_context(os.fdopen(write_fd, "wb"))
                result = subprocess.run(
                    [sys.executable, "-I", "-m", module, *args],
                    input=raw,
                    stdout=output,
                    stderr=errors,
                    check=False,
                    timeout=10,
                )
            expected_errors = None if close_errors else (diagnostic + os.linesep).encode("ascii")
            if (result.returncode, result.stdout, result.stderr) != (2, None, expected_errors):
                mode = "both" if close_errors else "stdout"
                raise AssertionError(
                    "closed_pipe_process_mismatch:" + module + ":" + name + ":" + mode
                )
            checked += 1
    return checked


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
    declaration_cases = sum(
        check_declaration(next(case for case in cases if case["id"] == name))
        for name in ("complete", "stale")
    )
    data = bundle_corpus(Path(sys.argv[2]))
    for case in data["cases"]:
        check_bundle_case(data, case)
    complete = next(case for case in cases if case["id"] == "complete")
    declaration_argument_cases = check_declaration_arguments(complete)
    declaration_boundary_cases = check_declaration_input_boundary(complete)
    declaration_malformed = check_declaration_malformed_inputs(complete)
    check_opaque_artifacts(complete)
    aggregate_artifact_cases = check_aggregate_artifacts(complete)
    exact_limit_cases = check_exact_limits(complete)
    assessment_malformed = check_malformed_frames(
        "qualification.assessment_cli",
        assessment_malformed_frames(arguments(complete)),
        "invalid_qualification_assessment",
    )
    complete_bundle = next(case for case in data["cases"] if case["id"] == "complete")
    bundle_exact_limit_cases = check_bundle_exact_limits(data, complete_bundle)
    bundle_scalar_boundary_cases = check_bundle_scalar_boundaries(data, complete_bundle)
    bundle_malformed = check_malformed_frames(
        "qualification.campaign_bundle_cli",
        bundle_malformed_frames(bundle_arguments(data, complete_bundle)),
        "invalid_campaign_bundle",
    )
    assessment_arguments = check_unexpected_arguments(
        "qualification.assessment_cli",
        frame(arguments(complete)),
        "invalid_qualification_assessment",
    )
    bundle_arguments_checked = check_unexpected_arguments(
        "qualification.campaign_bundle_cli",
        bundle_frame(bundle_arguments(data, complete_bundle)),
        "invalid_campaign_bundle",
    )
    declaration_frames, declaration_arguments = declaration_closed_pipe_inputs(cases)
    declaration_closed_pipes = check_closed_pipes(
        "qualification",
        declaration_frames,
        "invalid_qualification_manifest",
        case_arguments=declaration_arguments,
    )
    assessment_closed_pipes = check_closed_pipes(
        "qualification.assessment_cli",
        closed_pipe_frames(cases, lambda case: frame(arguments(case))),
        "invalid_qualification_assessment",
    )
    bundle_closed_pipes = check_closed_pipes(
        "qualification.campaign_bundle_cli",
        closed_pipe_frames(data["cases"], lambda case: bundle_frame(bundle_arguments(data, case))),
        "invalid_campaign_bundle",
    )
    print(
        json.dumps(
            {
                "assessment_vectors": 10,
                "declaration_cases": declaration_cases,
                "declaration_invalid_argument_cases": declaration_argument_cases,
                "declaration_exact_limit_cases": declaration_boundary_cases,
                "declaration_malformed_inputs": declaration_malformed,
                "declaration_closed_pipe_cases": declaration_closed_pipes,
                "bundle_vectors": 6,
                "artifact_vectors": 7,
                "assessment_opaque_artifact_cases": 1,
                "assessment_aggregate_artifact_cases": aggregate_artifact_cases,
                "assessment_exact_limit_cases": exact_limit_cases,
                "bundle_exact_limit_cases": bundle_exact_limit_cases,
                "bundle_scalar_boundary_cases": bundle_scalar_boundary_cases,
                "assessment_malformed_frames": assessment_malformed,
                "bundle_malformed_frames": bundle_malformed,
                "assessment_unexpected_argument_cases": assessment_arguments,
                "bundle_unexpected_argument_cases": bundle_arguments_checked,
                "assessment_closed_pipe_cases": assessment_closed_pipes,
                "bundle_closed_pipe_cases": bundle_closed_pipes,
                "isolated_install": True,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
