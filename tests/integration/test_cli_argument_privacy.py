"""Rejected CLI arguments must not become diagnostic output."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

EDGE = Path(__file__).resolve().parents[2] / "integrations/edge"
MARKER = "synthetic-private-argument-731"


class CLIArgumentPrivacy(unittest.TestCase):
    def invoke(self, *arguments, trace=False, module=False):
        env = os.environ.copy()
        env.pop("AETHRON_STARTUP_TRACE", None)
        if trace:
            env["AETHRON_STARTUP_TRACE"] = "1"
        entry = (
            "import runpy; runpy.run_module('aethron_edge', run_name='__main__')"
            if module
            else "from aethron_edge.cli import main; main()"
        )
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    "import sys; sys.path.insert(0, sys.argv.pop(1)); " + entry,
                    str(EDGE),
                    *arguments,
                ],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(list(Path(directory).iterdir()), [])
        return result

    def assert_private_trace_failure(self, result, *, module):
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertNotIn(MARKER, result.stderr)
        lines = result.stderr.splitlines()
        stages = ["process_entry", "cli_ready"] if module else ["cli_ready"]
        self.assertEqual(len(lines), len(stages) + 1)
        for line, stage in zip(lines[:-1], stages):
            self.assertRegex(line, rf"^AETHRON_STARTUP {stage} [0-9]+$")
        self.assertEqual(lines[-1], "invalid_request")

    def test_traced_argument_rejection_has_only_fixed_diagnostics(self):
        for module in (False, True):
            with self.subTest(module=module):
                result = self.invoke("doctor", "--" + MARKER, trace=True, module=module)
                self.assert_private_trace_failure(result, module=module)

    def test_traced_config_rejection_does_not_disclose_path_or_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / (MARKER + ".json")
            payload = '{"version":1,"' + MARKER + '":NaN}'
            path.write_text(payload, encoding="utf-8")
            for module in (False, True):
                with self.subTest(module=module):
                    result = self.invoke("doctor", "--config", str(path), trace=True, module=module)
                    self.assert_private_trace_failure(result, module=module)
            self.assertEqual(path.read_text(encoding="utf-8"), payload)

    def test_rejected_private_arguments_are_not_echoed(self):
        cases = (
            (MARKER,),
            ("doctor", "--" + MARKER),
            ("doctor", MARKER),
            ("doctor", "--replay-floor", MARKER),
            ("doctor", "--config", "--" + MARKER),
            ("doctor", "--help=" + MARKER),
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self.invoke(*arguments)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn(MARKER, result.stdout + result.stderr)
                self.assertEqual((result.stdout, result.stderr), ("", "invalid_request\n"))

    def test_missing_required_arguments_remain_errors(self):
        for arguments in ((), ("doctor",), ("doctor", "--config")):
            with self.subTest(arguments=arguments):
                result = self.invoke(*arguments)
                self.assertEqual(
                    (result.returncode, result.stdout, result.stderr),
                    (2, "", "invalid_request\n"),
                )

    def test_help_remains_available_without_configuration(self):
        result = self.invoke("--help")
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertIn("usage: aethron-edge", result.stdout)
        self.assertIn("--config", result.stdout)
        self.assertIn("doctor", result.stdout)
