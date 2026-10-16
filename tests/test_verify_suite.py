"""Standalone verification must observe a completed, nonempty test suite."""

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify
from tests import test_verify_static as static_checks


class VerificationSuite(unittest.TestCase):
    fixture = static_checks.StaticCheckClaims.fixture

    def probe(self, source):
        execute = subprocess.run
        runner = Path(verify.__file__).with_name("verification_suite.py")
        with self.fixture("value = 1") as (output, _):
            (verify.ROOT / "tests").mkdir()
            (verify.ROOT / "tests/test_fixture.py").write_text(source, encoding="utf-8")
            if runner.exists():
                (verify.ROOT / "scripts").mkdir()
                (verify.ROOT / "scripts/verification_suite.py").write_bytes(runner.read_bytes())
            calls, results = [], []

            def child(args, **kwargs):
                calls.append(args)
                if len(calls) == 2:
                    result = execute(
                        args, **dict(kwargs, capture_output=True, text=True, timeout=10)
                    )
                    results.append(result)
                    return result
                return subprocess.CompletedProcess(args, 0)

            with patch.object(verify.subprocess, "run", side_effect=child):
                try:
                    verify.run()
                except subprocess.CalledProcessError as error:
                    self.assertEqual(len(calls), 2)
                    self.assertEqual(output.getvalue(), "")
                    return error
            self.assertEqual(len(calls), 5)
            self.assertIn("PASS:", output.getvalue())
            return results[0]

    def assert_rejected(self, source):
        result = self.probe(source)
        self.assertIsInstance(result, subprocess.CalledProcessError)
        self.assertEqual(result.returncode, 1)
        self.assertIn("verification_suite_incomplete", result.stderr)

    def test_empty_or_partial_discovery_cannot_qualify(self):
        for source in (
            "",
            "import unittest\nclass Case(unittest.TestCase):\n"
            " def test_one(self): pass\n"
            " def test_two(self): self.fail('must execute')\n"
            "class Suite(unittest.TestSuite):\n"
            " def run(self, result, debug=False):\n"
            "  self._tests[0](result)\n  return result\n"
            "def load_tests(loader, tests, pattern):\n"
            " return Suite([Case('test_one'), Case('test_two')])\n",
        ):
            with self.subTest(source=source):
                self.assert_rejected(source)

    def test_suite_hooks_cannot_exit_before_completion(self):
        for code in (None, 0, 7):
            exit_call = f"sys.exit({code!r})"
            fixtures = (
                f"import sys\ndef load_tests(loader, tests, pattern):\n {exit_call}\n",
                "import sys, unittest\nclass Suite(unittest.TestSuite):\n"
                f" def countTestCases(self): {exit_call}\n"
                "def load_tests(loader, tests, pattern): return Suite()\n",
                "import sys, unittest\nclass Suite(unittest.TestSuite):\n"
                " def countTestCases(self): return 1\n"
                f" def run(self, result, debug=False): {exit_call}\n"
                "def load_tests(loader, tests, pattern): return Suite()\n",
            )
            for source in fixtures:
                with self.subTest(code=code, source=source):
                    self.assert_rejected(source)

    def test_test_failures_and_import_errors_remain_failures(self):
        for source in (
            "raise ValueError('synthetic import failure')\n",
            "import unittest\nclass Case(unittest.TestCase):\n"
            " def test_one(self): self.fail('synthetic failure')\n",
        ):
            with self.subTest(source=source):
                self.assert_rejected(source)

    def test_success_and_existing_platform_skips_remain_supported(self):
        base = (
            "import unittest\nclass Case(unittest.TestCase):\n"
            " def test_one(self): self.assertEqual(2 + 2, 4)\n"
        )
        for source in (
            base,
            base + " @unittest.skip('platform unavailable')\n def test_two(self): pass\n",
            base + " @unittest.expectedFailure\n def test_two(self): self.fail('known')\n",
        ):
            with self.subTest(source=source):
                result = self.probe(source)
                self.assertIsInstance(result, subprocess.CompletedProcess)
                self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
