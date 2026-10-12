"""Qualification commands must consume bounded binary input or fail closed."""

import io
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from qualification import __main__ as declaration
from qualification import campaign_bundle_cli as bundle
from qualification.tests.test_campaign_bundle_cli import ShortReads

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = (
    (declaration, "qualification", ["--now-ms", "1050"], "invalid_qualification_manifest\n"),
    (bundle, "qualification.campaign_bundle_cli", [], "invalid_campaign_bundle\n"),
)


class InputStreamTests(unittest.TestCase):
    def invoke(self, module, args, source):
        output, errors = io.StringIO(), io.StringIO()
        with (
            patch.object(sys, "argv", [module.__name__, *args]),
            patch.object(sys, "stdin", source),
            patch.object(sys, "stdout", output),
            patch.object(sys, "stderr", errors),
        ):
            status = module.main()
        self.assertFalse(output.closed)
        self.assertFalse(errors.closed)
        return status, output.getvalue(), errors.getvalue()

    def test_unavailable_binary_input_has_fixed_failure(self):
        for module, _, args, diagnostic in COMMANDS:
            for source in (None, io.StringIO("PRIVATE"), SimpleNamespace(buffer=None)):
                with self.subTest(module=module.__name__, source=type(source).__name__):
                    self.assertEqual(self.invoke(module, args, source), (2, "", diagnostic))
                    if isinstance(source, io.StringIO):
                        self.assertFalse(source.closed)
                        self.assertEqual(source.tell(), 0)

    def test_process_without_stdin_exits_two_without_traceback(self):
        for _, name, args, diagnostic in COMMANDS:
            with self.subTest(module=name):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-E",
                        "-c",
                        "import runpy, sys; name = sys.argv.pop(1); sys.stdin = None; "
                        "runpy.run_module(name, run_name='__main__')",
                        name,
                        *args,
                    ],
                    capture_output=True,
                    cwd=ROOT,
                    timeout=10,
                    check=False,
                )
                self.assertEqual(
                    (result.returncode, result.stdout, result.stderr), (2, b"", diagnostic.encode())
                )

    def test_declaration_short_reads_preserve_golden_report(self):
        raw = (ROOT / "qualification/rigs/synthetic-v1.json").read_bytes()
        source = ShortReads(raw)
        self.assertEqual(
            self.invoke(declaration, ["--now-ms", "1050"], SimpleNamespace(buffer=source)),
            (0, (ROOT / "qualification/evidence/synthetic-report-v1.json").read_text(), ""),
        )
        self.assertFalse(source.closed)

    def test_declaration_valid_prefix_cannot_hide_trailing_input(self):
        raw = (ROOT / "qualification/rigs/synthetic-v1.json").read_bytes()

        class PrefixRead(io.BytesIO):
            def read(self, size=-1):
                return super().read(min(size, len(raw)))

        for suffix in (b"PRIVATE invalid tail", b" " * 65537):
            with self.subTest(suffix_length=len(suffix)):
                source = PrefixRead(raw + suffix)
                self.assertEqual(
                    self.invoke(declaration, ["--now-ms", "1050"], SimpleNamespace(buffer=source)),
                    (2, "", "invalid_qualification_manifest\n"),
                )
                self.assertLessEqual(source.tell(), 65537)
                self.assertFalse(source.closed)

    def test_declaration_exact_byte_limit_is_accepted(self):
        raw = (ROOT / "qualification/rigs/synthetic-v1.json").read_bytes()
        source = ShortReads(raw + b" " * (65536 - len(raw)))
        result = self.invoke(declaration, ["--now-ms", "1050"], SimpleNamespace(buffer=source))
        self.assertEqual((result[0], result[2]), (0, ""))
        self.assertEqual(source.tell(), 65536)

    def test_invalid_read_results_fail_without_echoing_input(self):
        class InvalidRead:
            def __init__(self, value):
                self.value = value

            def read(self, size):
                return self.value

        for value in (None, "PRIVATE", bytearray(b"PRIVATE"), b"x" * 65538):
            with self.subTest(value_type=type(value).__name__):
                self.assertEqual(
                    self.invoke(
                        declaration,
                        ["--now-ms", "1050"],
                        SimpleNamespace(buffer=InvalidRead(value)),
                    ),
                    (2, "", "invalid_qualification_manifest\n"),
                )


if __name__ == "__main__":
    unittest.main()
