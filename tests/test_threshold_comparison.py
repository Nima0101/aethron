"""Held-out source imbalance, snapshot isolation and real comparison CLI."""

import json
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_threshold_experiment as fixtures


@unittest.skipIf(
    getattr(fixtures.ThresholdExperiment, "__unittest_skip__", False), "POSIX required"
)
class ThresholdComparison(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ThresholdExperiment()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        original = f.doc["provenance"][0]
        f.doc["provenance"] += [
            dict(original, id="private_strong", source="private strong declaration"),
            dict(original, id="private_weak", source="private weak declaration"),
        ]
        template = next(row for row in f.doc["samples"] if row["split"] == "test")
        f.doc["samples"] = [row for row in f.doc["samples"] if row["split"] != "test"]
        f.labels["test"]["samples"] = []
        for index in range(11):
            pixels = bytearray([210 + index] * 64)
            boxes = [[0.375, 0.375, 0.25, 0.25]]
            if index < 10:
                for point in (27, 28, 35, 36):
                    pixels[point] = 0 if index < 9 else 255
            else:
                pixels = bytearray([110] * 64)
                boxes = []
            data = b"P5\n8 8\n255\n" + pixels
            digest = fixtures.digest(data)
            (f.blobs / digest).write_bytes(data)
            row = dict(
                template,
                id=f"private_test_{index}",
                artifact_sha256=digest,
                source_sha256=digest,
                provenance_id="private_weak" if index == 9 else "private_strong",
            )
            f.doc["samples"].append(row)
            f.labels["test"]["samples"].append(
                {"sample_id": row["id"], "artifact_sha256": digest, "boxes": boxes}
            )
        f.bind()
        self.model = f.fit()

    def compare(self, **changes):
        f = self.fixture
        api = f.api()
        self.assertTrue(callable(getattr(api, "compare", None)), "comparison API missing")
        args = f.args("test")
        args["expected_candidate_sha256"] = fixtures.digest(self.model)
        args.update(changes)
        return api.compare(self.model, f.manifest, f.blobs, "test", **args)

    def test_comparison_exposes_missed_source_despite_high_pooled_recall(self):
        report = self.compare()
        self.assertEqual(report["comparison"], "pgm_threshold_comparison_v1")
        self.assertEqual(report["version"], 1)
        self.assertEqual(
            [row["baseline"] for row in report["reports"]],
            [
                "experimental_pgm_threshold_v1",
                "classical_pgm_obstacle_v1",
                "global_pgm_obstacle_v1",
            ],
        )
        for row, fp in zip(report["reports"], [0, 0, 1]):
            self.assertEqual(row["version"], 2)
            self.assertEqual(row["frames"], 11)
            self.assertEqual(
                row["metrics"],
                {
                    "true_positives": 9,
                    "false_positives": fp,
                    "false_negatives": 1,
                    "precision": 0.9 if fp else 1.0,
                    "recall": 0.9,
                },
            )
            groups = row["metrics_by_provenance"]
            self.assertEqual(sorted(g["frames"] for g in groups.values()), [1, 10])
            weak = next(g for g in groups.values() if g["frames"] == 1)
            self.assertEqual(
                weak,
                {
                    "frames": 1,
                    "true_positives": 0,
                    "false_positives": 0,
                    "false_negatives": 1,
                    "precision": None,
                    "recall": 0.0,
                },
            )
            for key in ("true_positives", "false_positives", "false_negatives"):
                self.assertEqual(sum(g[key] for g in groups.values()), row["metrics"][key])
            self.assertEqual(list(groups), sorted(groups))
            self.assertEqual(row["manifest_sha256"], fixtures.digest(self.fixture.manifest))
            self.assertEqual(
                row["annotations_sha256"], self.fixture.args("test")["expected_annotations_sha256"]
            )
            self.assertFalse(row["qualified"])
        experiment = report["reports"][0]
        self.assertEqual(experiment["threshold"], 63)
        self.assertEqual(experiment["candidate_sha256"], fixtures.digest(self.model))
        self.assertEqual(experiment["training"], "pinned_train_threshold")
        self.assertFalse(experiment["training_verified"])
        self.assertEqual([r["training"] for r in report["reports"][1:]], ["none", "none"])
        for flag in ("rights_verified", "signatures_verified", "training_verified", "qualified"):
            self.assertIs(report[flag], False)
        self.assertNotIn("private_", json.dumps(report))
        self.assertNotIn("private strong declaration", json.dumps(report))
        self.assertNotIn(str(self.fixture.root), json.dumps(report))

    def test_comparison_uses_one_verified_snapshot_and_never_refits(self):
        expected = self.compare()
        api = self.fixture.api()
        original = api.detect_threshold_pgm
        path = self.fixture.blobs / self.fixture.doc["samples"][-1]["artifact_sha256"]

        def replace_during_first_detector(data, threshold):
            path.write_bytes(b"tampered while comparing")
            return original(data, threshold)

        with (
            patch.object(api, "detect_threshold_pgm", replace_during_first_detector),
            patch.object(api, "fit", side_effect=AssertionError("held-out refit")),
        ):
            self.assertEqual(self.compare(), expected)
        with self.assertRaisesRegex(ValueError, "^invalid_threshold_experiment$"):
            self.compare()

    def test_provenance_bindings_match_existing_reports_and_reordering_is_stable(self):
        from aethron.evaluation import proposals

        f = self.fixture
        report = self.compare()
        fixed = proposals.run(
            f.manifest, f.blobs, "test", baseline="all", per_provenance=True, **f.args("test")
        )
        self.assertEqual(report["reports"][1:], fixed["reports"])
        groups = [r["metrics_by_provenance"] for r in report["reports"]]
        f.doc["provenance"].reverse()
        f.doc["samples"].reverse()
        f.labels["test"]["samples"].reverse()
        f.bind()
        self.model = f.fit()
        self.assertEqual([r["metrics_by_provenance"] for r in self.compare()["reports"]], groups)
        f.doc["provenance"][0]["source"] = "changed original declaration"
        f.bind()
        self.model = f.fit()
        self.assertNotEqual(
            set(self.compare()["reports"][0]["metrics_by_provenance"]), set(groups[0])
        )

    def test_bad_pins_and_work_budgets_fail_before_comparison(self):
        api = self.fixture.api()
        self.compare()
        with patch.object(
            api, "detect_threshold_pgm", side_effect=AssertionError("invalid inference")
        ):
            for key in (
                "expected_candidate_sha256",
                "expected_annotations_sha256",
                "expected_manifest_sha256",
                "expected_protocol_sha256",
            ):
                with (
                    self.subTest(key=key),
                    self.assertRaisesRegex(ValueError, "^invalid_threshold_experiment$"),
                ):
                    self.compare(**{key: "0" * 64})
            for name, value in (("MAX_FRAMES", 10), ("MAX_PIXELS", 703)):
                with (
                    patch.object(api, name, value),
                    self.assertRaisesRegex(ValueError, "^invalid_threshold_experiment$"),
                ):
                    self.compare()

    def test_cli_emits_complete_comparison_or_fixed_error(self):
        f = self.fixture
        model = f.root / "model.json"
        manifest = f.root / "manifest.json"
        labels = f.root / "labels.json"
        model.write_bytes(self.model)
        manifest.write_bytes(f.manifest)
        labels.write_bytes(f.args("test")["annotations"])
        command = [
            sys.executable,
            "-m",
            "aethron.evaluation.threshold",
            "compare",
            str(manifest),
            "--blob-dir",
            str(f.blobs),
            "--manifest-sha256",
            fixtures.digest(f.manifest),
            "--protocol-sha256",
            fixtures.PROTOCOL_SHA256,
            "--annotations",
            str(labels),
            "--annotations-sha256",
            fixtures.digest(labels.read_bytes()),
            "--split",
            "test",
            "--candidate",
            str(model),
            "--candidate-sha256",
            fixtures.digest(self.model),
        ]
        result = subprocess.run(command, capture_output=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.compare())
        labels.write_bytes(b"private malformed labels")
        result = subprocess.run(command, capture_output=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"invalid_threshold_experiment\n")
