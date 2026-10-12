"""Exercise raw assessment framing and real consumers against portable vectors."""

import contextlib
import copy
import io
import json
import os
import struct
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qualification.tests import test_assessment_vectors as vectors
from qualification.tests.test_campaign_bundle_cli import NoReadPastHeader, ShortReads
from qualification.tests.test_report_output import Output

ROOT = Path(__file__).resolve().parents[2]
MAGIC = b"AETHRON-QUALIFICATION-ASSESSMENT-V1\n"
DIAGNOSTIC = "invalid_qualification_assessment\n"
# Process text streams use native newlines; the binary frame always uses LF.
PROCESS_DIAGNOSTIC = ("invalid_qualification_assessment" + os.linesep).encode("ascii")


def uint(value):
    return struct.pack(">I", value)


def blob(raw):
    return uint(len(raw)) + raw


def byte_map(entries):
    return uint(len(entries)) + b"".join(key.encode("ascii") + blob(raw) for key, raw in entries)


def frame(args):
    plan, captures, domain, procedure, methods = args
    parts = [MAGIC, blob(plan), blob(domain), blob(procedure), byte_map(methods.items())]
    parts.append(uint(len(captures)))
    for row in captures:
        parts += [
            blob(row["case_id"].encode("ascii")),
            blob(json.dumps(row["now_ms"]).encode("ascii")),
            blob(row["manifest"]),
            byte_map(row["artifacts"].items()),
        ]
    return b"".join(parts)


class AssessmentCliTests(unittest.TestCase):
    def setUp(self):
        from qualification import assessment_cli

        self.command = assessment_cli
        self.vectors = vectors.AssessmentVectorTests()
        self.cases = self.vectors.corpus()
        self.args = self.vectors.arguments(next(c for c in self.cases if c["id"] == "complete"))

    def invoke(self, raw, args=()):
        source = io.BytesIO(raw) if type(raw) is bytes else raw
        out, err = io.StringIO(), io.StringIO()
        with (
            patch.object(sys, "argv", ["assessment_cli", *args]),
            patch.object(sys, "stdin", SimpleNamespace(buffer=source)),
            patch.object(sys, "stdout", out),
            patch.object(sys, "stderr", err),
        ):
            status = self.command.main()
        self.assertFalse(out.closed)
        self.assertFalse(err.closed)
        return status, out.getvalue(), err.getvalue()

    def test_all_portable_vectors_through_real_process(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                result = subprocess.run(
                    [sys.executable, "-E", "-m", "qualification.assessment_cli"],
                    input=frame(self.vectors.arguments(case)),
                    capture_output=True,
                    cwd=ROOT,
                    timeout=10,
                    check=False,
                )
                if case["expected_error"]:
                    self.assertEqual(
                        (result.returncode, result.stdout, result.stderr),
                        (2, b"", PROCESS_DIAGNOSTIC),
                    )
                else:
                    self.assertEqual(result.returncode, 0 if case["id"] == "complete" else 1)
                    self.assertEqual(result.stderr, b"")
                    self.vectors.exact(json.loads(result.stdout), case["expected_report"])
                    self.assertEqual(
                        result.stdout,
                        (
                            json.dumps(
                                case["expected_report"], sort_keys=True, separators=(",", ":")
                            )
                            + os.linesep
                        ).encode(),
                    )

    def test_binary_process_input_preserves_opaque_artifact_bytes(self):
        args = copy.deepcopy(self.args)
        # Text-mode stdin on Windows would translate CRLF and stop at Ctrl-Z.
        artifacts = args[1][0]["artifacts"]
        self.assertTrue(artifacts)
        for digest in artifacts:
            artifacts[digest] += b"\r\n\x1a\x00\xffPRIVATE"
        expected = self.command.evaluate(*args)
        self.assertFalse(expected["artifact_bytes_verified"])
        self.assertFalse(expected["software_checks_passed"])
        result = subprocess.run(
            [sys.executable, "-E", "-m", "qualification.assessment_cli"],
            input=frame(args),
            capture_output=True,
            cwd=ROOT,
            timeout=10,
            check=False,
        )
        self.assertEqual((result.returncode, result.stderr), (1, b""))
        self.vectors.exact(json.loads(result.stdout), expected)
        self.assertNotIn(b"PRIVATE", result.stdout)

    def test_short_reads_preserve_exact_report(self):
        raw = frame(self.args)
        expected = self.invoke(raw)
        self.assertEqual(expected[0], 0)
        self.assertEqual(self.invoke(ShortReads(raw)), expected)

    def test_every_truncation_and_trailing_data_fail_before_evaluation(self):
        raw = frame(self.args)
        with patch.object(self.command, "evaluate") as evaluate:
            for size in range(len(raw)):
                self.assertEqual(self.invoke(raw[:size]), (2, "", DIAGNOSTIC), size)
            for malformed in (b"?" + raw[1:], raw + b"PRIVATE", raw + raw):
                self.assertEqual(self.invoke(malformed), (2, "", DIAGNOSTIC))
            evaluate.assert_not_called()

    def test_lengths_rejected_before_payload_read(self):
        plan, rows, domain, procedure, methods = self.args
        docs = MAGIC + blob(plan) + blob(domain) + blob(procedure)
        methods_frame = docs + byte_map(methods.items())
        row = rows[0]
        capture = methods_frame + uint(1) + blob(row["case_id"].encode())
        instant = blob(json.dumps(row["now_ms"]).encode("ascii"))
        manifest = capture + instant + blob(row["manifest"])
        for header in (
            MAGIC + uint(65537),
            MAGIC + blob(plan) + uint(65537),
            MAGIC + blob(plan) + blob(domain) + uint(65537),
            docs + uint(49),
            docs + uint(1) + b"a" * 64 + uint(65537),
            methods_frame + uint(65),
            methods_frame + uint(1) + uint(65),
            capture + uint(18),
            capture + instant + uint(65537),
            manifest + uint(16),
            manifest + uint(1) + b"a" * 64 + uint(1048577),
        ):
            with self.subTest(header=header[-16:]):
                self.assertEqual(self.invoke(NoReadPastHeader(header)), (2, "", DIAGNOSTIC))

    def test_duplicate_and_invalid_hash_keys_fail_before_value_read(self):
        plan, rows, domain, procedure, _ = self.args
        docs = MAGIC + blob(plan) + blob(domain) + blob(procedure)
        row = rows[0]
        capture = (
            docs
            + uint(0)
            + uint(1)
            + blob(row["case_id"].encode())
            + blob(json.dumps(row["now_ms"]).encode("ascii"))
            + blob(row["manifest"])
        )
        for prefix in (docs, capture):
            for key in (b"A" * 64, b"\xff" * 64, b"g" * 64):
                self.assertEqual(
                    self.invoke(NoReadPastHeader(prefix + uint(1) + key)), (2, "", DIAGNOSTIC)
                )
            duplicate = prefix + uint(2) + b"a" * 64 + blob(b"abc") + b"a" * 64
            self.assertEqual(self.invoke(NoReadPastHeader(duplicate)), (2, "", DIAGNOSTIC))

    def test_aggregate_artifact_limit_is_checked_across_captures_before_read(self):
        plan, rows, domain, procedure, methods = self.args
        row = rows[0]
        capture = blob(row["case_id"].encode()) + blob(json.dumps(row["now_ms"]).encode("ascii"))
        capture += blob(row["manifest"])
        prefix = MAGIC + blob(plan) + blob(domain) + blob(procedure) + byte_map(methods.items())
        artifacts = [(str(index) * 64, b"x" * 1048576) for index in range(4)]
        header = prefix + uint(2) + capture + byte_map(artifacts)
        header += capture + uint(1) + b"0" * 64 + uint(1)
        self.assertEqual(self.invoke(NoReadPastHeader(header)), (2, "", DIAGNOSTIC))

    def test_exact_limits_admit_opaque_bytes_without_inventing_qualification(self):
        args = copy.deepcopy(self.args)
        plan, rows, domain, procedure, methods = args
        methods.clear()
        methods.update((f"{i:064x}", b"\xff" * 65536) for i in range(48))
        row = rows[0]
        row["manifest"] += b" " * (65536 - len(row["manifest"]))
        row["case_id"] = "a" * 64
        row["artifacts"] = {f"{i:064x}": b"\xff" * 1048576 for i in range(4)}
        row["artifacts"].update((f"{i:064x}", b"") for i in range(4, 15))
        rows.extend(dict(row, artifacts={}) for _ in range(63))
        args = tuple(raw + b" " * (65536 - len(raw)) if type(raw) is bytes else raw for raw in args)
        status, output, errors = self.invoke(frame(args))
        self.assertEqual((status, errors), (1, ""))
        self.assertFalse(json.loads(output)["physical_qualification_passed"])
        from qualification.assessment import evaluate

        self.vectors.exact(json.loads(output), evaluate(*args))

    def test_invalid_read_results_and_exceptions_have_fixed_error(self):
        class BadRead:
            def __init__(self, value):
                self.value = value

            def read(self, size):
                if isinstance(self.value, Exception):
                    raise self.value
                return self.value

        for value in (
            None,
            "PRIVATE",
            bytearray(b"PRIVATE"),
            b"x" * 65538,
            OSError("PRIVATE"),
            ValueError("PRIVATE"),
        ):
            self.assertEqual(self.invoke(BadRead(value)), (2, "", DIAGNOSTIC))
        self.assertEqual(self.invoke(frame(self.args), ["--PRIVATE"]), (2, "", DIAGNOSTIC))

    def test_output_failure_cannot_return_success(self):
        for output in (None, Output("write"), Output("flush")):
            errors = io.StringIO()
            with (
                patch.object(sys, "argv", ["assessment_cli"]),
                patch.object(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(frame(self.args)))),
                patch.object(sys, "stdout", output),
                patch.object(sys, "stderr", errors),
            ):
                self.assertEqual(self.command.main(), 2)
            self.assertEqual(errors.getvalue(), DIAGNOSTIC)

    def test_missing_input_and_failed_diagnostics_preserve_failure(self):
        closed = io.StringIO()
        closed.close()
        for source in (None, io.StringIO("PRIVATE"), SimpleNamespace(buffer=None)):
            for errors in (None, closed, Output("write"), Output("flush")):
                output = io.StringIO()
                with (
                    patch.object(sys, "argv", ["assessment_cli"]),
                    patch.object(sys, "stdin", source),
                    patch.object(sys, "stdout", output),
                    patch.object(sys, "stderr", errors),
                ):
                    self.assertEqual(self.command.main(), 2)
                self.assertEqual(output.getvalue(), "")
                self.assertFalse(output.closed)

    def test_real_closed_pipes_preserve_exit_two(self):
        negative = next(case for case in self.cases if case["id"] == "stale")
        for raw in (frame(self.args), frame(self.vectors.arguments(negative)), b"PRIVATE"):
            for close_errors in (False, True):
                with contextlib.ExitStack() as stack:
                    read_fd, write_fd = os.pipe()
                    os.close(read_fd)
                    output = stack.enter_context(os.fdopen(write_fd, "wb"))
                    errors = subprocess.PIPE
                    if close_errors:
                        read_fd, write_fd = os.pipe()
                        os.close(read_fd)
                        errors = stack.enter_context(os.fdopen(write_fd, "wb"))
                    result = subprocess.run(
                        [sys.executable, "-E", "-m", "qualification.assessment_cli"],
                        input=raw,
                        stdout=output,
                        stderr=errors,
                        cwd=ROOT,
                        timeout=10,
                        check=False,
                    )
                self.assertEqual(result.returncode, 2)
                if not close_errors:
                    self.assertEqual(result.stderr, PROCESS_DIAGNOSTIC)

    def test_instants_are_not_coerced_and_names_are_validated(self):
        for value in (True, False, 1050.0, "1050", None, [], {}, -1, 2**53, float("inf")):
            args = copy.deepcopy(self.args)
            args[1][0]["now_ms"] = value
            self.assertEqual(self.invoke(frame(args)), (2, "", DIAGNOSTIC))
        for name in ("", "PRIVATE name", "a/b"):
            args = copy.deepcopy(self.args)
            args[1][0]["case_id"] = name
            self.assertEqual(self.invoke(frame(args)), (2, "", DIAGNOSTIC))

    def test_empty_submission_retains_negative_report(self):
        args = copy.deepcopy(self.args)
        args[1].clear()
        args[4].clear()
        status, output, errors = self.invoke(frame(args))
        self.assertEqual((status, errors), (1, ""))
        report = json.loads(output)
        self.assertFalse(report["artifact_bytes_verified"])
        self.assertFalse(report["software_checks_passed"])
        self.assertEqual(report["captures"], [])


if __name__ == "__main__":
    unittest.main()
