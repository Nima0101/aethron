"""Package evidence must not run with its assertion checks disabled."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/edge_package_check.py"


class PackageEvidenceMode(unittest.TestCase):
    def invoke_help(self, flags=(), optimize=None):
        env = os.environ.copy()
        env.pop("PYTHONOPTIMIZE", None)
        if optimize is not None:
            env["PYTHONOPTIMIZE"] = optimize
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, *flags, str(SCRIPT), "--help"],
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self.assertEqual(list(Path(directory).iterdir()), [])
        return result

    def test_optimized_modes_reject_before_cli_or_build(self):
        for flags, optimize in ((("-O",), None), (("-OO",), None), ((), "1"), ((), "2")):
            with self.subTest(flags=flags, optimize=optimize):
                result = self.invoke_help(flags, optimize)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "package_check_requires_assertions\n")

    def test_normal_mode_retains_help_without_building(self):
        for optimize in (None, "0"):
            with self.subTest(optimize=optimize):
                result = self.invoke_help(optimize=optimize)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("--wheelhouse", result.stdout)
                self.assertEqual(result.stderr, "")
