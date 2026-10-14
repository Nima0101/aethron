"""Optimized Python must not qualify tests after removing their assertions."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class VerificationSuiteMode(unittest.TestCase):
    def probe(self, *, flags=(), optimize=None, condition="False", module=True):
        runner = Path(__file__).resolve().parents[1] / "scripts/verification_suite.py"
        env = dict(os.environ, PYTHONNOUSERSITE="1")
        for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONOPTIMIZE"):
            env.pop(key, None)
        if optimize is not None:
            env["PYTHONOPTIMIZE"] = optimize
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts").mkdir()
            (root / "scripts/__init__.py").write_text("", encoding="utf-8")
            (root / "scripts/verification_suite.py").write_bytes(runner.read_bytes())
            (root / "tests").mkdir()
            (root / "tests/test_fixture.py").write_text(
                "import unittest\nprint('suite_imported')\n"
                "class Case(unittest.TestCase):\n"
                f" def test_assertion(self): assert {condition}\n",
                encoding="utf-8",
            )
            entry = (
                ["-m", "scripts.verification_suite"]
                if module
                else ["scripts/verification_suite.py"]
            )
            return subprocess.run(
                [sys.executable, *flags, *entry],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

    def test_optimized_modes_reject_before_discovery(self):
        for module in (True, False):
            for flags, optimize in ((("-O",), None), (("-OO",), None), ((), "1"), ((), "2")):
                with self.subTest(module=module, flags=flags, optimize=optimize):
                    result = self.probe(flags=flags, optimize=optimize, module=module)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(result.stderr, "verification_suite_requires_assertions\n")

    def test_normal_modes_execute_and_preserve_assertion_failures(self):
        for module in (True, False):
            for optimize in (None, "0"):
                for condition, expected in (("True", 0), ("False", 1)):
                    with self.subTest(module=module, optimize=optimize, condition=condition):
                        result = self.probe(optimize=optimize, condition=condition, module=module)
                        self.assertEqual(result.returncode, expected, result.stderr)
                        self.assertEqual(result.stdout, "suite_imported\n")
                        self.assertIn("Ran 1 test", result.stderr)
                        if expected:
                            self.assertIn("AssertionError", result.stderr)
                            self.assertIn("verification_suite_incomplete", result.stderr)
                        else:
                            self.assertIn("OK", result.stderr)


if __name__ == "__main__":
    unittest.main()
