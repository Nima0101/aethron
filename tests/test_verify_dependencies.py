"""Verifier dependency diagnostics in subprocesses without site packages."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = """
import runpy
import subprocess
import sys
from pathlib import Path

def unexpected_child(*args, **kwargs):
    raise RuntimeError('dependency check must precede child execution')

subprocess.run = unexpected_child
subprocess.check_output = unexpected_child
sys.path.insert(0, str(Path(sys.argv[1]).parent))
sys.path.insert(0, sys.argv[2])
runpy.run_path(sys.argv[1], run_name='__main__')
"""


class VerificationDependencies(unittest.TestCase):
    def invoke(self, script, directory):
        return subprocess.run(
            [sys.executable, "-I", "-S", "-c", PROBE, str(ROOT / script), str(directory)],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def test_missing_parser_has_actionable_diagnostic_before_children(self):
        for script in ("scripts/verify.py", "scripts/public_links.py"):
            with self.subTest(script=script), tempfile.TemporaryDirectory() as directory:
                result = self.invoke(script, directory)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertEqual(
                    result.stderr,
                    "missing verification dependency: markdown-it-py; install with this interpreter: "
                    "python -m pip install --require-hashes -r requirements-links.lock\n",
                )
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_unrelated_import_failure_is_not_reported_as_missing_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "markdown_it.py").write_text(
                "raise ModuleNotFoundError('synthetic dependency failure', "
                "name='synthetic_transitive')\n",
                encoding="utf-8",
            )
            result = self.invoke("scripts/markdown_links.py", directory)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("ModuleNotFoundError: synthetic dependency failure", result.stderr)
            self.assertNotIn("install with this interpreter", result.stderr)
