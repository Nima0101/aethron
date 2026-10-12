"""Check pinned assessment vectors using only an isolated installed distribution.

Run with the consumer venv's Python -I, outside the checkout, and pass the corpus
path. The corpus supplies bytes and expected results, never executable helpers.
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
from qualification.assessment import evaluate

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


def main():
    if not sys.flags.isolated or sys.prefix == sys.base_prefix:
        raise RuntimeError("isolated_consumer_venv_required")
    for module in (aethron, qualification):
        # Do not resolve sys.executable: POSIX venvs can symlink the base binary.
        if Path(sys.prefix).resolve() not in Path(module.__file__).resolve().parents:
            raise RuntimeError("installed_module_required")
    for case in corpus(Path(sys.argv[1])):
        check_case(case)
    print(json.dumps({"assessment_vectors": 10, "isolated_install": True}, sort_keys=True))


if __name__ == "__main__":
    main()
