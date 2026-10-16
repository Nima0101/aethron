"""Standalone suite evidence must belong to the runner's own checkout."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class VerificationSuiteRoot(unittest.TestCase):
    def probe(self, *, location, module, passing=False):
        runner = Path(__file__).resolve().parents[1] / "scripts/verification_suite.py"
        env = dict(os.environ, PYTHONNOUSERSITE="1")
        for key in ("PYTHONHOME", "PYTHONPATH", "PYTHONOPTIMIZE"):
            env.pop(key, None)
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "checkout"
            (root / "scripts").mkdir(parents=True)
            (root / "scripts/__init__.py").write_text("", encoding="utf-8")
            entry = root / "scripts/verification_suite.py"
            entry.write_bytes(runner.read_bytes())
            cwd = {
                "root": root,
                "parent": parent,
                "sibling": parent / "unrelated",
                "nested": root / "nested",
            }[location]
            cwd.mkdir(exist_ok=True)
            for folder, label, success in ((root, "checkout", passing), (cwd, "foreign", True)):
                if folder == root and label == "foreign":
                    continue
                (folder / "tests").mkdir()
                (folder / "tests/test_fixture.py").write_text(
                    f"import unittest\nprint('{label}_imported')\n"
                    "class Case(unittest.TestCase):\n"
                    f" def test_one(self): self.assertTrue({success!r})\n",
                    encoding="utf-8",
                )
            if module:
                # Select the real runner while leaving discovery's cwd foreign.
                env["PYTHONPATH"] = str(root)
                args = ["-m", "scripts.verification_suite"]
            else:
                args = [str(entry)]
            return subprocess.run(
                [sys.executable, *args],
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

    def test_foreign_working_directory_rejected_before_discovery(self):
        for location in ("parent", "sibling", "nested"):
            for module in (False, True):
                with self.subTest(location=location, module=module):
                    result = self.probe(location=location, module=module)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(result.stderr, "verification_suite_wrong_root\n")

    def test_own_checkout_executes_and_preserves_failures(self):
        for module in (False, True):
            for passing in (False, True):
                with self.subTest(module=module, passing=passing):
                    result = self.probe(location="root", module=module, passing=passing)
                    self.assertEqual(result.returncode, 0 if passing else 1, result.stderr)
                    self.assertEqual(result.stdout, "checkout_imported\n")
                    self.assertIn("Ran 1 test", result.stderr)
                    self.assertNotIn("verification_suite_wrong_root", result.stderr)


if __name__ == "__main__":
    unittest.main()
