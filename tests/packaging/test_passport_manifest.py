"""Bounded source-selection check, not an archive build or wheel qualification."""

import importlib.util
import unittest
from pathlib import Path

from setuptools._distutils.filelist import FileList

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "passport_sdist_check", ROOT / "scripts/passport_sdist_check.py"
)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class PassportManifestTests(unittest.TestCase):
    def test_source_distribution_selects_consumer_inputs(self):
        required = CHECKER.required_inputs(ROOT)
        for path in required:
            self.assertTrue((ROOT / path).is_file(), f"missing checkout input: {path}")
        # Only the finite published consumer inputs are candidates in this probe.
        # Unrelated manifest patterns can legitimately warn that they matched no files.
        selected = FileList()
        selected.set_allfiles(sorted(required))
        for line in (ROOT / "MANIFEST.in").read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                selected.process_template_line(line)
        self.assertEqual(sorted(required - set(selected.files)), [], "consumer inputs omitted")


if __name__ == "__main__":
    unittest.main()
