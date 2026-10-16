"""A later interrupted test must not erase already observed failure diagnostics."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class VerificationSuiteDiagnostics(unittest.TestCase):
    def probe(self, source, *, interrupt):
        runner = Path(__file__).resolve().parents[1] / "scripts/verification_suite.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "scripts/__init__.py").touch()
            (root / "scripts/verification_suite.py").write_bytes(runner.read_bytes())
            (root / "tests").mkdir()
            suffix = "class ZLater(unittest.TestCase):\n def test_later(self):\n" + (
                "  os._exit(7)\n" if interrupt else "  pass\n"
            )
            (root / "tests/test_fixture.py").write_text(
                "import os, unittest\n" + source + suffix, encoding="utf-8"
            )
            return subprocess.run(
                [sys.executable, "-m", "scripts.verification_suite"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

    def test_failures_survive_abrupt_later_exit(self):
        cases = (
            (
                "class AFirst(unittest.TestCase):\n"
                " def test_first(self): self.fail('assertion sentinel')\n",
                "FAIL:",
                "AssertionError: assertion sentinel",
            ),
            (
                "class AFirst(unittest.TestCase):\n"
                " def test_first(self): raise ValueError('error sentinel')\n",
                "ERROR:",
                "ValueError: error sentinel",
            ),
            (
                "class AFirst(unittest.TestCase):\n"
                " @classmethod\n"
                " def setUpClass(cls): raise RuntimeError('fixture sentinel')\n"
                " def test_first(self): pass\n",
                "ERROR: setUpClass",
                "RuntimeError: fixture sentinel",
            ),
            (
                "class AFirst(unittest.TestCase):\n"
                " def test_first(self):\n"
                "  with self.subTest(value=17): self.fail('subtest sentinel')\n",
                "value=17",
                "AssertionError: subtest sentinel",
            ),
            (
                "class AFirst(unittest.TestCase):\n"
                " def test_first(self):\n"
                "  with self.subTest(value=23): raise ValueError('suberror sentinel')\n",
                "value=23",
                "ValueError: suberror sentinel",
            ),
            (
                "class AFirst(unittest.TestCase):\n"
                " @unittest.expectedFailure\n"
                " def test_first(self): pass\n",
                "UNEXPECTED SUCCESS:",
                "test_first",
            ),
        )
        for source, label, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic):
                result = self.probe(source, interrupt=True)
                self.assertEqual(result.returncode, 7, result.stderr)
                self.assertIn(label, result.stderr)
                self.assertIn(diagnostic, result.stderr)
                self.assertNotIn("Ran ", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_completed_failure_keeps_summary_and_rejection(self):
        result = self.probe(
            "class AFirst(unittest.TestCase):\n"
            " def test_first(self): self.fail('assertion sentinel')\n",
            interrupt=False,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("AssertionError: assertion sentinel", result.stderr)
        self.assertIn("Ran 2 tests", result.stderr)
        self.assertIn("FAILED (failures=1)", result.stderr)
        self.assertIn("verification_suite_incomplete", result.stderr)

    def test_skips_expected_failures_and_passes_keep_success(self):
        result = self.probe(
            "class AFirst(unittest.TestCase):\n"
            " @unittest.expectedFailure\n"
            " def test_expected(self): self.fail('expected sentinel')\n"
            " @unittest.skip('unavailable')\n"
            " def test_skip(self): pass\n",
            interrupt=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Ran 3 tests", result.stderr)
        self.assertIn("OK (skipped=1, expected failures=1)", result.stderr)
        self.assertNotIn("expected sentinel", result.stderr)


if __name__ == "__main__":
    unittest.main()
