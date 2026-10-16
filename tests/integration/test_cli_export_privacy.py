"""Offline export filesystem errors must not disclose caller paths."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aethron_edge.openapi import document

EDGE = Path(__file__).resolve().parents[2] / "integrations/edge"
MARKER = "synthetic-private-export-732"


class CLIExportPrivacy(unittest.TestCase):
    def invoke(self, directory, output):
        env = os.environ.copy()
        env.pop("AETHRON_STARTUP_TRACE", None)
        return subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                "import sys; sys.path.insert(0, sys.argv.pop(1)); "
                "from aethron_edge.cli import main; main()",
                str(EDGE),
                "export-openapi",
                "--out",
                str(output),
            ],
            cwd=directory,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def assert_private_failure(self, result):
        self.assertNotIn(MARKER, result.stdout + result.stderr)
        self.assertEqual(
            (result.returncode, result.stdout, result.stderr),
            (2, "", "export_failed\n"),
        )

    def test_output_directory_error_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / MARKER
            output.mkdir()
            result = self.invoke(directory, output)
            self.assertEqual(list(output.iterdir()), [])
            self.assert_private_failure(result)

    def test_parent_file_error_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / MARKER
            parent.write_bytes(b"preserve-existing-file")
            result = self.invoke(directory, parent / "schema.json")
            self.assertEqual(parent.read_bytes(), b"preserve-existing-file")
            self.assert_private_failure(result)

    def test_successful_export_preserves_document(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "schema.json"
            result = self.invoke(directory, output)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
            self.assertEqual(json.loads(output.read_text()), document())
