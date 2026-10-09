"""Strict artifact checks distinguish pixel drift from PNG encoding drift."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(Image is None, "Pillow required for visual reproduction diagnostics")
class VisualReproduction(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.reference = Path(self.temp.name) / "expected"
        self.produced = Path(self.temp.name) / "produced"
        self.reference.mkdir()
        self.produced.mkdir()

    def api(self):
        spec = importlib.util.spec_from_file_location(
            "verify_visuals", ROOT / "scripts/verify_visuals.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_cli_reports_encoding_difference_without_passing_it(self):
        image = Image.new("RGB", (8, 8), "red")
        for folder, level in ((self.reference, 0), (self.produced, 9)):
            for name in (
                "perception-day.png",
                "perception-night.png",
                "perception-occlusion.png",
                "perception-unknown.png",
            ):
                image.save(folder / name, compress_level=level)
            for name in (
                "perception.gif",
                "perception-input.jsonl",
                "perception-output.json",
                "perception.html",
                "perception-manifest.json",
            ):
                (folder / name).write_bytes(b"same fixture")
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/verify_visuals.py"),
                str(self.produced),
                "--reference",
                str(self.reference),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stdout.startswith("{"), "missing structured mismatch diagnosis")
        report = json.loads(result.stdout)
        self.assertFalse(report["byte_identical"])
        self.assertEqual(len(report["differences"]), 4)
        for row in report["differences"]:
            self.assertEqual(row["reason"], "png_encoding")
            self.assertEqual(row["expected_pixels_sha256"], row["actual_pixels_sha256"])
            self.assertNotEqual(row["expected_sha256"], row["actual_sha256"])

    def test_changed_pixels_missing_files_and_exact_matches(self):
        api = self.api()
        for name in api.ARTIFACTS:
            for folder in (self.reference, self.produced):
                (folder / name).write_bytes(b"same fixture")
        self.assertTrue(api.verify(self.produced, self.reference)["byte_identical"])
        Image.new("RGB", (8, 8), "red").save(self.reference / "perception-day.png")
        Image.new("RGB", (8, 8), "blue").save(self.produced / "perception-day.png")
        report = api.verify(self.produced, self.reference)
        self.assertFalse(report["byte_identical"])
        self.assertEqual(report["differences"][0]["reason"], "png_pixels")
        (self.produced / "perception-day.png").unlink()
        self.assertEqual(
            api.verify(self.produced, self.reference)["differences"][0]["reason"],
            "missing_or_unreadable",
        )
