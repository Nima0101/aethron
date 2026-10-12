"""A failed diagnostic endpoint must not replace the fixed command failure."""

import contextlib
import io
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qualification import __main__ as declaration
from qualification import campaign_bundle_cli as bundle
from qualification._process_exit import finish
from qualification.tests.test_campaign_bundle_cli import frame
from qualification.tests.test_report_output import Output

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = (
    (declaration, "qualification", ["--now-ms", "1050"]),
    (bundle, "qualification.campaign_bundle_cli", []),
)


class DiagnosticOutputTests(unittest.TestCase):
    def test_absent_report_stream_cannot_report_success(self):
        for module, name, args in COMMANDS:
            with self.subTest(module=name):
                raw = (
                    (ROOT / "qualification/rigs/synthetic-v1.json").read_bytes()
                    if module is declaration
                    else frame()
                )
                errors = io.StringIO()
                with (
                    patch.object(sys, "argv", [name, *args]),
                    patch.object(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(raw))),
                    patch.object(sys, "stdout", None),
                    contextlib.redirect_stderr(errors),
                ):
                    self.assertEqual(module.main(), 2)
                expected = (
                    "invalid_qualification_manifest\n"
                    if module is declaration
                    else "invalid_campaign_bundle\n"
                )
                self.assertEqual(errors.getvalue(), expected)
                self.assertFalse(errors.closed)

    def test_absent_diagnostic_stream_never_redirects_into_report_stream(self):
        for module, name, args in COMMANDS:
            with self.subTest(module=name):
                output = io.StringIO()
                with (
                    patch.object(sys, "argv", [name, *args]),
                    patch.object(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"invalid"))),
                    contextlib.redirect_stdout(output),
                    patch.object(sys, "stderr", None),
                ):
                    self.assertEqual(module.main(), 2)
                self.assertEqual(output.getvalue(), "")
                self.assertFalse(output.closed)

    def test_module_finalization_accepts_absent_process_streams(self):
        with patch.object(sys, "stdout", None), patch.object(sys, "stderr", None):
            self.assertEqual(finish(2), 2)

    def test_already_closed_diagnostic_stream_does_not_escape_or_reopen(self):
        for module, name, args in COMMANDS:
            with self.subTest(module=name):
                output, errors = io.StringIO(), io.StringIO()
                errors.close()
                with (
                    patch.object(sys, "argv", [name, *args]),
                    patch.object(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(b"invalid"))),
                    contextlib.redirect_stdout(output),
                    contextlib.redirect_stderr(errors),
                ):
                    self.assertEqual(module.main(), 2)
                self.assertTrue(errors.closed)
                self.assertFalse(output.closed)
                self.assertEqual(output.getvalue(), "")

    def test_library_diagnostic_failure_preserves_status_and_stream_ownership(self):
        for module, name, args in COMMANDS:
            for failure in ("write", "flush"):
                with self.subTest(module=name, failure=failure):
                    output, errors = io.StringIO(), Output(failure)
                    source = SimpleNamespace(buffer=io.BytesIO(b"PRIVATE invalid input"))
                    with (
                        patch.object(sys, "argv", [name, *args]),
                        patch.object(sys, "stdin", source),
                        contextlib.redirect_stdout(output),
                        contextlib.redirect_stderr(errors),
                    ):
                        try:
                            status = module.main()
                        except OSError:
                            status = "escaped_diagnostic_error"
                    self.assertEqual(status, 2)
                    self.assertFalse(output.closed)
                    self.assertFalse(errors.closed)
                    self.assertEqual(output.getvalue(), "")
                    self.assertNotIn("PRIVATE", errors.getvalue())
                    if failure == "flush":
                        self.assertGreater(errors.flushes, 0)

    def test_real_closed_diagnostic_pipe_preserves_exit_two(self):
        for _, name, args in COMMANDS:
            for close_stdout in (False, True):
                with self.subTest(module=name, close_stdout=close_stdout):
                    raw = b"PRIVATE invalid input"
                    if close_stdout:
                        raw = (
                            (ROOT / "qualification/rigs/synthetic-v1.json").read_bytes()
                            if name == "qualification"
                            else frame()
                        )
                    with contextlib.ExitStack() as stack:
                        read_fd, write_fd = os.pipe()
                        os.close(read_fd)
                        errors = stack.enter_context(os.fdopen(write_fd, "wb"))
                        output = subprocess.PIPE
                        if close_stdout:
                            read_fd, write_fd = os.pipe()
                            os.close(read_fd)
                            output = stack.enter_context(os.fdopen(write_fd, "wb"))
                        result = subprocess.run(
                            [sys.executable, "-E", "-m", name, *args],
                            input=raw,
                            stdout=output,
                            stderr=errors,
                            cwd=ROOT,
                            timeout=10,
                            check=False,
                        )
                    self.assertEqual(result.returncode, 2)
                    if not close_stdout:
                        self.assertEqual(result.stdout, b"")
