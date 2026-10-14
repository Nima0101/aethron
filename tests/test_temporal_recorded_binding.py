"""Recorded evaluation must use the frozen inventory and annotations."""

import contextlib
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import temporal_evaluate as temporal


class TemporalRecordedBinding(unittest.TestCase):
    def test_modified_manifest_cannot_publish_success(self):
        source = temporal.ROOT
        for case in ("shortened", "truth_removed", "truth_changed", "image_rebound"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(source / "data/aot", root / "data/aot")
                freeze = root / "docs/verification/data-v3-freeze.json"
                freeze.parent.mkdir(parents=True)
                shutil.copyfile(source / "docs/verification/data-v3-freeze.json", freeze)
                manifest_path = root / "data/aot/manifest.json"
                manifest = json.loads(manifest_path.read_bytes())
                if case == "shortened":
                    manifest["frames"] = manifest["frames"][:1]
                elif case == "truth_removed":
                    for item in manifest["frames"]:
                        item["truth"] = []
                elif case == "truth_changed":
                    manifest["frames"][0]["truth"][0]["box"] = [0.1, 0.1, 0.1, 0.1]
                else:
                    item = manifest["frames"][0]
                    image = root / "data/aot" / item["file"]
                    image.write_bytes(b"changed-image")
                    item["sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
                manifest_path.write_text(json.dumps(manifest))
                output = root / "output"
                output.mkdir()
                report_path = output / "temporal-evaluation.json"
                report_path.write_text('{"passed": true, "stale": true}')
                with (
                    patch.object(temporal, "ROOT", root),
                    patch.object(temporal, "synthetic_fixture_paths", return_value=[]),
                    patch.object(temporal, "benchmark", return_value={"passed": True}),
                    patch.object(temporal, "detect_pgm", return_value=[]) as detector,
                    patch.object(
                        temporal,
                        "estimate_translation",
                        return_value={"dx": 0.0, "dy": 0.0, "variance": 0.05, "valid": False},
                    ),
                    contextlib.redirect_stdout(io.StringIO()) as stdout,
                ):
                    with self.assertRaisesRegex(ValueError, "^recorded_manifest_digest$"):
                        temporal.run(output)
                detector.assert_not_called()
                self.assertEqual(stdout.getvalue(), "")
                report = json.loads(report_path.read_bytes())
                self.assertIs(report["passed"], False)
                self.assertEqual(report["failure_stage"], "recorded")
                self.assertNotIn("recorded", report)
                self.assertNotIn("stale", report)
                self.assertFalse((output / "recorded-input.jsonl").exists())
                self.assertFalse((output / "recorded-output.json").exists())

    def test_frozen_manifest_is_consumed_without_rereading(self):
        manifest_path = temporal.ROOT / "data/aot/manifest.json"
        payload = manifest_path.read_bytes()
        original = Path.read_bytes
        reads = []

        def read(path):
            if path == manifest_path:
                reads.append(path)
                return payload if len(reads) == 1 else b"{}"
            return original(path)

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(Path, "read_bytes", read),
                patch.object(temporal, "detect_pgm", return_value=[]),
                patch.object(
                    temporal,
                    "estimate_translation",
                    return_value={"dx": 0.0, "dy": 0.0, "variance": 0.05, "valid": False},
                ),
            ):
                report = temporal.recorded(Path(directory))
            self.assertEqual(reads, [manifest_path])
            self.assertEqual(report["frames"], 25)
            self.assertEqual(report["temporal"]["false_negatives"], 20)
            self.assertIs(report["physical_or_semantic_qualification"], False)


if __name__ == "__main__":
    unittest.main()
