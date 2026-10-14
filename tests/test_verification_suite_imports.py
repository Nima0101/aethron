"""Direct suite invocation must exercise checkout packages before foreign copies."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class VerificationSuiteImports(unittest.TestCase):
    def probe(self, *, module, passing, foreign):
        runner = Path(__file__).resolve().parents[1] / "scripts/verification_suite.py"
        env = dict(os.environ, PYTHONNOUSERSITE="1")
        for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONOPTIMIZE"):
            env.pop(key, None)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "checkout"
            (root / "scripts").mkdir(parents=True)
            (root / "scripts/__init__.py").write_text("", encoding="utf-8")
            (root / "scripts/verification_suite.py").write_bytes(runner.read_bytes())
            (root / "tests").mkdir()
            (root / "tests/test_fixture.py").write_text(
                "import unittest, fixture_package\n"
                "class Case(unittest.TestCase):\n"
                " def test_one(self): self.assertTrue(fixture_package.value)\n",
                encoding="utf-8",
            )
            package = root / "fixture_package"
            package.mkdir()
            (package / "__init__.py").write_text(
                f"print('checkout_imported')\nvalue = {passing!r}\n", encoding="utf-8"
            )
            if foreign:
                alternate = Path(directory) / "foreign"
                (alternate / "fixture_package").mkdir(parents=True)
                (alternate / "fixture_package/__init__.py").write_text(
                    f"print('foreign_imported')\nvalue = {not passing!r}\n", encoding="utf-8"
                )
                env["PYTHONPATH"] = str(alternate)
            entry = (
                ["-m", "scripts.verification_suite"]
                if module
                else ["scripts/verification_suite.py"]
            )
            return subprocess.run(
                [sys.executable, *entry],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

    def test_checkout_packages_import_without_installation(self):
        for module in (False, True):
            for passing in (False, True):
                with self.subTest(module=module, passing=passing):
                    result = self.probe(module=module, passing=passing, foreign=False)
                    self.assertEqual(result.stdout, "checkout_imported\n", result.stderr)
                    self.assertEqual(result.returncode, 0 if passing else 1, result.stderr)
                    self.assertIn("Ran 1 test", result.stderr)

    def test_foreign_packages_cannot_hide_failures_or_break_success(self):
        for module in (False, True):
            for passing in (False, True):
                with self.subTest(module=module, passing=passing):
                    result = self.probe(module=module, passing=passing, foreign=True)
                    self.assertEqual(result.returncode, 0 if passing else 1, result.stderr)
                    self.assertEqual(result.stdout, "checkout_imported\n", result.stderr)
                    self.assertIn("Ran 1 test", result.stderr)
                    if not passing:
                        self.assertIn("AssertionError", result.stderr)
                        self.assertIn("verification_suite_incomplete", result.stderr)


if __name__ == "__main__":
    unittest.main()
