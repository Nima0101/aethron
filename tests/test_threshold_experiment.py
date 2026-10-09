"""Original synthetic regressions for train-only fitting and held-out evaluation."""

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_dataset_artifacts as artifact_fixtures

from aethron.evaluation import synthetic
from aethron.evaluation.annotations import PROTOCOL_SHA256


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encode(doc):
    return (json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode()


@unittest.skipIf(
    getattr(artifact_fixtures.DatasetArtifacts, "__unittest_skip__", False), "POSIX required"
)
class ThresholdExperiment(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.blobs = self.root / "blobs"
        self.blobs.mkdir()
        blobs, manifest, labels, _ = synthetic._dataset()
        for key, value in blobs.items():
            (self.blobs / key).write_bytes(value)
        self.doc = json.loads(manifest)
        self.labels = {split: json.loads(raw) for split, raw in labels.items()}
        # A threshold below40 misses; 63 and95 tie; 127 also invents an obstacle
        # on the unrelated uniform training negative. Optimum is therefore63.
        row = next(row for row in self.doc["samples"] if row["id"] == "train_match")
        image = (self.blobs / row["artifact_sha256"]).read_bytes().replace(b"\x00", b"\x28")
        row["source_sha256"] = row["artifact_sha256"] = digest(image)
        (self.blobs / digest(image)).write_bytes(image)
        self.labels["train"]["samples"][0]["artifact_sha256"] = digest(image)
        self.bind()

    def bind(self):
        self.manifest = encode(self.doc)
        for labels in self.labels.values():
            labels["manifest_sha256"] = digest(self.manifest)

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("aethron.evaluation.threshold"))
        return importlib.import_module("aethron.evaluation.threshold")

    def args(self, split):
        raw = encode(self.labels[split])
        return {
            "annotations": raw,
            "expected_annotations_sha256": digest(raw),
            "expected_manifest_sha256": digest(self.manifest),
            "expected_protocol_sha256": PROTOCOL_SHA256,
        }

    def fit(self, **changes):
        args = self.args("train")
        args.update(changes)
        return self.api().fit(self.manifest, self.blobs, **args)

    def evaluate(self, model, split="test", **changes):
        args = self.args(split if type(split) is str and split in self.labels else "test")
        args["expected_candidate_sha256"] = digest(model)
        args.update(changes)
        return self.api().evaluate(model, self.manifest, self.blobs, split, **args)

    def test_fit_uses_only_pinned_train_labels_and_deterministic_ties(self):
        api = self.api()
        with patch.object(api, "detect_threshold_pgm", wraps=api.detect_threshold_pgm) as detector:
            model = self.fit()
        train = {
            (self.blobs / row["artifact_sha256"]).read_bytes()
            for row in self.doc["samples"]
            if row["split"] == "train"
        }
        self.assertEqual(len(detector.call_args_list), 21)
        self.assertTrue(all(call.args[0] in train for call in detector.call_args_list))
        doc = json.loads(model)
        self.assertEqual(doc["threshold"], 63)
        self.assertEqual(doc["training_split"], "train")
        self.assertEqual(
            doc["training_annotations_sha256"], self.args("train")["expected_annotations_sha256"]
        )
        self.assertEqual(doc["training_manifest_sha256"], digest(self.manifest))
        self.assertEqual(doc["preprocessing_sha256"], digest(api.PREPROCESSING_BYTES))
        self.assertEqual(doc["search_sha256"], digest(api.SEARCH_BYTES))
        self.assertEqual(self.fit(), model)
        for split in ("validation", "test"):
            with self.assertRaisesRegex(ValueError, "^invalid_threshold_experiment$"):
                self.fit(**self.args(split))
            # No held-out label file is read by fit, even if malformed/missing.
            (self.root / f"annotations-{split}.json").write_bytes(
                b"private invalid held-out labels"
            )
            self.labels[split]["samples"] = []
        self.assertEqual(self.fit(), model)

    def test_training_labels_change_fit_but_held_out_labels_only_change_metrics(self):
        model = self.fit()
        api = self.api()
        with patch.object(api, "fit", side_effect=AssertionError("evaluation refit")):
            report = self.evaluate(model)
        self.assertEqual(
            report["metrics"],
            {
                "true_positives": 1,
                "false_positives": 0,
                "false_negatives": 1,
                "precision": 1.0,
                "recall": 0.5,
            },
        )
        self.assertEqual(report["candidate_sha256"], digest(model))
        self.assertEqual(report["metrics_by_evidence"]["synthetic"]["frames"], 3)
        for flag in ("qualified", "rights_verified", "signatures_verified", "training_verified"):
            self.assertIs(report[flag], False)
        for row in self.labels["test"]["samples"]:
            row["boxes"] = []
        changed = self.evaluate(model)
        self.assertEqual(changed["metrics"]["false_positives"], 1)
        self.assertEqual(changed["candidate_sha256"], report["candidate_sha256"])
        self.assertEqual(self.fit(), model)
        for row in self.labels["train"]["samples"]:
            row["boxes"] = []
        self.assertEqual(json.loads(self.fit())["threshold"], 31)
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("test_match", json.dumps(report))

    def test_pins_closed_model_schema_and_held_out_split_reject_before_detection(self):
        api = self.api()
        model = self.fit()
        for key in self.args("train"):
            if key.startswith("expected_"):
                with (
                    self.subTest(key=key),
                    self.assertRaisesRegex(ValueError, "^invalid_threshold_experiment$"),
                ):
                    self.fit(**{key: "0" * 64})
        cases = [b"[]", b"NaN", b"\xff", model[:-2] + b',"version":1}\n', b" " * 4097]
        for key, value in (
            ("version", True),
            ("threshold", True),
            ("threshold", 32),
            ("training_split", "test"),
            ("preprocessing_sha256", "0" * 64),
            ("search_sha256", "0" * 64),
            ("training_manifest_sha256", "0" * 64),
            ("protocol_sha256", "0" * 64),
            ("training_annotations_sha256", "bad"),
            ("private_note", "secret"),
        ):
            doc = json.loads(model)
            doc[key] = value
            cases.append(encode(doc))
        for key in json.loads(model):
            doc = json.loads(model)
            del doc[key]
            cases.append(encode(doc))
        with patch.object(
            api, "detect_threshold_pgm", side_effect=AssertionError("invalid inference")
        ):
            for raw in cases:
                with (
                    self.subTest(raw=raw[:70]),
                    self.assertRaisesRegex(ValueError, "^invalid_threshold_experiment$"),
                ):
                    self.evaluate(raw)
            for split in ("train", "unknown", True, []):
                with self.assertRaisesRegex(ValueError, "^invalid_threshold_experiment$"):
                    self.evaluate(model, split=split)
            with self.assertRaisesRegex(ValueError, "^invalid_threshold_experiment$"):
                self.evaluate(model, expected_candidate_sha256="0" * 64)

    def test_work_budget_preflight_and_dataset_tampering_reject_before_fit(self):
        api = self.api()
        with patch.object(
            api, "detect_threshold_pgm", side_effect=AssertionError("overbudget inference")
        ):
            for name, value in (("MAX_FRAMES", 2), ("MAX_PIXELS", 191)):
                with (
                    patch.object(api, name, value),
                    self.assertRaisesRegex(ValueError, "^invalid_threshold_experiment$"),
                ):
                    self.fit()
        with patch.object(api, "MAX_PIXELS", 192), patch.object(api, "MAX_FRAMES", 3):
            self.assertEqual(json.loads(self.fit())["threshold"], 63)
        row = next(row for row in self.doc["samples"] if row["split"] == "test")
        (self.blobs / row["artifact_sha256"]).write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "^invalid_threshold_experiment$"):
            self.fit()

    def test_exact_objective_and_false_positive_tie_break(self):
        api = self.api()
        # Equal F1, different TP/FP: prefer fewer FP rather than more TP.
        counts = {31: [1, 0, 1], 63: [2, 1, 1]}
        with patch.object(
            api, "_counts", side_effect=lambda _, __, t: (counts.get(t, [0, 1, 1]), {})
        ):
            self.assertEqual(json.loads(self.fit())["threshold"], 31)
            # Both F1 values round to .499875 at six decimals; 63 is strictly
            # better and must win despite its extra FP. Counts fit the work caps.
            counts.update({31: [1000, 1000, 1001], 63: [1001, 1001, 1002]})
            self.assertEqual(json.loads(self.fit())["threshold"], 63)

    def test_held_out_pixels_are_not_decoded_and_fit_uses_verified_snapshot(self):
        api = self.api()
        row = next(row for row in self.doc["samples"] if row["split"] == "test")
        raw = b"original non-PGM held-out software fixture"
        row["artifact_sha256"] = row["source_sha256"] = digest(raw)
        (self.blobs / digest(raw)).write_bytes(raw)
        self.bind()
        model = self.fit()
        self.assertEqual(json.loads(model)["threshold"], 63)
        train = next(row for row in self.doc["samples"] if row["id"] == "train_match")
        path = self.blobs / train["artifact_sha256"]
        original = api.detect_threshold_pgm

        def replace_after_load(data, threshold):
            path.write_bytes(b"tampered after verified snapshot")
            return original(data, threshold)

        with patch.object(api, "detect_threshold_pgm", replace_after_load):
            self.assertEqual(self.fit(), model)
        with self.assertRaisesRegex(ValueError, "^invalid_threshold_experiment$"):
            self.fit()

    def test_parameter_boundary_and_pinned_annotation_substitution(self):
        api = self.api()
        image = b"P5\n3 1\n255\n" + bytes([63] * 3)
        self.assertEqual(len(api.detect_threshold_pgm(image, 63)), 1)
        self.assertEqual(api.detect_threshold_pgm(image, 62), [])
        for value in (True, None, -1, 256, 63.0, "63"):
            with self.assertRaisesRegex(ValueError, "^invalid_threshold$"):
                api.detect_threshold_pgm(image, value)
        # Relabeling the split string cannot substitute held-out sample IDs/blobs.
        labels = dict(self.labels["test"], split="train")
        raw = encode(labels)
        with self.assertRaisesRegex(ValueError, "^invalid_threshold_experiment$"):
            self.fit(annotations=raw, expected_annotations_sha256=digest(raw))

    def test_cli_fit_evaluate_and_fixed_errors(self):
        model = self.fit()
        manifest = self.root / "manifest.json"
        manifest.write_bytes(self.manifest)
        labels = self.root / "labels.json"
        labels.write_bytes(encode(self.labels["train"]))
        command = [
            sys.executable,
            "-m",
            "aethron.evaluation.threshold",
            "fit",
            str(manifest),
            "--blob-dir",
            str(self.blobs),
            "--manifest-sha256",
            digest(self.manifest),
            "--protocol-sha256",
            PROTOCOL_SHA256,
            "--annotations",
            str(labels),
            "--annotations-sha256",
            digest(labels.read_bytes()),
        ]
        result = subprocess.run(command, capture_output=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, model)
        candidate = self.root / "candidate.json"
        candidate.write_bytes(result.stdout)
        labels.write_bytes(encode(self.labels["test"]))
        command[3] = "evaluate"
        command[-1] = digest(labels.read_bytes())
        command += [
            "--split",
            "test",
            "--candidate",
            str(candidate),
            "--candidate-sha256",
            digest(model),
        ]
        result = subprocess.run(command, capture_output=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.evaluate(model))
        for kind in ("symlink", "fifo", "malformed"):
            candidate.unlink()
            if kind == "symlink":
                candidate.symlink_to(manifest)
            elif kind == "fifo":
                os.mkfifo(candidate)
            else:
                candidate.write_bytes(b"private malformed input")
            result = subprocess.run(command, capture_output=True, timeout=10, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            self.assertEqual(result.stderr, b"invalid_threshold_experiment\n")
