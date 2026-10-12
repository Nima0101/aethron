"""Report delivery failures must not escape the declaration command boundary."""

import io
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qualification import __main__ as command

ROOT = Path(__file__).resolve().parents[1]


class Output(io.StringIO):
    def __init__(self, failure=None):
        super().__init__()
        self.failure = failure
        self.flushes = 0

    def write(self, value):
        if self.failure == "write":
            raise OSError("PRIVATE output endpoint")
        return super().write(value)

    def flush(self):
        self.flushes += 1
        if self.failure == "flush":
            raise OSError("PRIVATE output endpoint")
        return super().flush()


class ReportOutputTests(unittest.TestCase):
    def invoke(self, output, rig="synthetic-v1.json"):
        errors = io.StringIO()
        source = SimpleNamespace(buffer=io.BytesIO((ROOT / "rigs" / rig).read_bytes()))
        with (
            patch.object(command.sys, "argv", ["qualification", "--now-ms", "1050"]),
            patch.object(command.sys, "stdin", source),
            patch.object(command.sys, "stdout", output),
            patch.object(command.sys, "stderr", errors),
        ):
            try:
                status = command.main()
            except OSError:
                status = "escaped_output_error"
        return status, errors.getvalue()

    def test_write_error_returns_fixed_failure(self):
        output = Output("write")
        self.assertEqual(self.invoke(output), (2, "invalid_qualification_manifest\n"))
        self.assertEqual(output.getvalue(), "")

    def test_flush_error_cannot_return_success(self):
        output = Output("flush")
        self.assertEqual(self.invoke(output), (2, "invalid_qualification_manifest\n"))
        # Output accepted before a flush failure cannot be retracted.
        self.assertTrue(output.getvalue())
        self.assertNotIn("PRIVATE", output.getvalue())

    def test_valid_and_negative_reports_flush_without_changing_bytes(self):
        for rig, expected, status in (
            ("synthetic-v1.json", "synthetic-report-v1.json", 0),
            ("expired-calibration-v1.json", "expired-calibration-report-v1.json", 1),
        ):
            with self.subTest(rig=rig):
                output = Output()
                self.assertEqual(self.invoke(output, rig), (status, ""))
                self.assertEqual(output.getvalue(), (ROOT / "evidence" / expected).read_text())
                self.assertGreater(output.flushes, 0)


if __name__ == "__main__":
    unittest.main()
