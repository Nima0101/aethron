"""Run held-out comparisons from a moved bundle with independent annotation pins."""

import json
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_threshold_bundle_reader as fixtures

from aethron.evaluation import threshold, threshold_bundle


@unittest.skipIf(
    getattr(fixtures.ThresholdBundleReader, "__unittest_skip__", False), "POSIX required"
)
class BundleComparison(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ThresholdBundleReader()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.data = self.fixture.fixture.fixture
        self.bindings = self.fixture.bindings
        self.labels = self.data.args("test")

    def compare(self, split="test", **changes):
        self.assertTrue(
            callable(getattr(threshold_bundle, "compare", None)), "bundle comparison missing"
        )
        args = dict(self.labels, **self.bindings)
        args.update(changes)
        return threshold_bundle.compare(self.root, split, **args)

    def test_relocated_comparison_matches_existing_held_out_metrics_without_refit(self):
        expected = threshold.compare(
            self.fixture.fixture.model,
            self.data.manifest,
            self.data.blobs,
            "test",
            expected_candidate_sha256=self.fixture.pins["model_sha256"],
            **self.labels,
        )
        self.data.blobs.rename(self.root.with_name("source-unavailable"))
        moved = self.root.with_name("moved")
        self.root.rename(moved)
        self.root = moved
        with patch.object(threshold, "fit", side_effect=AssertionError("no refit")):
            report = self.compare()
        self.assertEqual(report["comparison"], expected)
        self.assertTrue(report["bundle_verification"]["bundle_verified"])
        self.assertEqual(
            report["bundle_verification"]["candidate_sha256"], self.fixture.pins["candidate_sha256"]
        )
        self.assertFalse(report["qualified"])
        self.assertNotIn(str(self.root), json.dumps(report))
        for row in report["comparison"]["reports"]:
            self.assertIn("metrics_by_provenance", row)
            self.assertFalse(row["qualified"])

    def test_train_stale_annotations_and_incomplete_bundle_reject_before_detectors(self):
        with patch.object(
            threshold, "detect_threshold_pgm", side_effect=AssertionError("must not run")
        ):
            for split, changes in (
                ("train", {}),
                ("test", {"expected_annotations_sha256": "0" * 64}),
                ("test", {"expected_candidate_sha256": "0" * 64}),
            ):
                with (
                    self.subTest(split=split, changes=changes),
                    self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"),
                ):
                    self.compare(split, **changes)
            (self.root / "pins.json").unlink()
            with self.assertRaisesRegex(ValueError, "^invalid_threshold_bundle$"):
                self.compare()

    def test_cli_reports_metrics_then_fixed_error_without_partial_stdout(self):
        labels = self.root.with_name("test-annotations.json")
        labels.write_bytes(self.labels["annotations"])
        command = [
            sys.executable,
            "-m",
            "aethron.evaluation.threshold_bundle_compare",
            str(self.root),
            "--split",
            "test",
            "--annotations",
            str(labels),
            "--annotations-sha256",
            self.labels["expected_annotations_sha256"],
        ]
        for key, value in self.bindings.items():
            command += ["--" + key.removeprefix("expected_").replace("_", "-"), value]
        result = subprocess.run(command, capture_output=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.compare())
        labels.write_bytes(b"private changed annotation")
        result = subprocess.run(command, capture_output=True, timeout=10, check=False)
        self.assertEqual(
            (result.returncode, result.stdout, result.stderr),
            (2, b"", b"invalid_threshold_bundle\n"),
        )
