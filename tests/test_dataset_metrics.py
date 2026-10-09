"""Hand-checked obstacle metrics on original synthetic PGM samples."""

import copy
import hashlib
import importlib
import json
import subprocess
import sys
import unittest

import test_dataset_proposals as fixtures

# Protocol fixed before running any candidate: inclusive IoU0.3, maximum cardinality,
# then maximum total IoU; normalized xywh, no temporal identity metrics.
PROTOCOL = (
    b'{"version":1,"task":"obstacle_proposals","iou_min":0.3,'
    b'"matching":"max_cardinality_then_iou","box":"normalized_xywh",'
    b'"max_boxes_per_frame":64}\n'
)
BOX = [0.375, 0.375, 0.25, 0.25]


@unittest.skipIf(getattr(fixtures.DatasetProposals, "__unittest_skip__", False), "POSIX required")
class DatasetMetrics(unittest.TestCase):
    def setUp(self):
        self.images = fixtures.DatasetProposals()
        self.images.setUp()
        self.addCleanup(self.images.doCleanups)
        self.fixture = self.images.fixture
        self.fixture.doc["protocol_sha256"] = hashlib.sha256(PROTOCOL).hexdigest()
        (self.fixture.root / self.fixture.doc["protocol_sha256"]).write_bytes(PROTOCOL)
        self.doc = {
            "version": 1,
            "manifest_sha256": hashlib.sha256(self.fixture.raw()).hexdigest(),
            "protocol_sha256": self.fixture.doc["protocol_sha256"],
            "split": "test",
            "samples": [
                {
                    "sample_id": "test",
                    "artifact_sha256": self.fixture.doc["samples"][2]["artifact_sha256"],
                    "boxes": [BOX],
                }
            ],
        }

    def run_metrics(self, doc=None, raw=None, pin=None):
        raw = json.dumps(self.doc if doc is None else doc).encode() if raw is None else raw
        return self.images.run_baseline(
            annotations=raw,
            expected_annotations_sha256=hashlib.sha256(raw).hexdigest() if pin is None else pin,
        )

    def test_real_pixels_match_miss_false_positive_and_empty_truth(self):
        for boxes, counts, precision, recall in (
            ([BOX], (1, 0, 0), 1.0, 1.0),
            ([], (0, 1, 0), 0.0, None),
            ([[0, 0, 0.1, 0.1]], (0, 1, 1), 0.0, 0.0),
            ([BOX, [0, 0, 0.1, 0.1]], (1, 0, 1), 1.0, 0.5),
        ):
            with self.subTest(boxes=boxes):
                self.doc["samples"][0]["boxes"] = boxes
                result = self.run_metrics()
                metrics = result["metrics"]
                self.assertEqual(
                    tuple(
                        metrics[k] for k in ("true_positives", "false_positives", "false_negatives")
                    ),
                    counts,
                )
                self.assertEqual(metrics["precision"], precision)
                self.assertEqual(metrics["recall"], recall)
                self.assertFalse(result["qualified"])
                self.assertFalse(result["rights_verified"])
                self.assertEqual(result["proposal_count"], 1)
                self.assertEqual(
                    result["annotations_sha256"],
                    hashlib.sha256(json.dumps(self.doc).encode()).hexdigest(),
                )
                self.assertNotIn("sample_id", json.dumps(result))
        self.images.image(2, fixtures.pgm(230))
        self.doc["manifest_sha256"] = hashlib.sha256(self.fixture.raw()).hexdigest()
        self.doc["samples"][0].update(
            artifact_sha256=self.fixture.doc["samples"][2]["artifact_sha256"], boxes=[]
        )
        metrics = self.run_metrics()["metrics"]
        self.assertEqual(
            metrics,
            {
                "true_positives": 0,
                "false_positives": 0,
                "false_negatives": 0,
                "precision": None,
                "recall": None,
            },
        )

    def test_wrong_binding_missing_duplicate_or_extra_rows_reject(self):
        bad = []
        for key, value in (
            ("manifest_sha256", "0" * 64),
            ("protocol_sha256", "0" * 64),
            ("split", "train"),
            ("version", True),
        ):
            doc = copy.deepcopy(self.doc)
            doc[key] = value
            bad.append(doc)
        for key, value in (("sample_id", "train"), ("artifact_sha256", "0" * 64)):
            doc = copy.deepcopy(self.doc)
            doc["samples"][0][key] = value
            bad.append(doc)
        for rows in ([], self.doc["samples"] * 2):
            doc = copy.deepcopy(self.doc)
            doc["samples"] = rows
            bad.append(doc)
        doc = copy.deepcopy(self.doc)
        doc["samples"][0]["person_id"] = "forbidden"
        bad.append(doc)
        for doc in bad:
            with self.subTest(doc=doc), self.assertRaisesRegex(ValueError, "^invalid_annotations$"):
                self.run_metrics(doc)
        with self.assertRaisesRegex(ValueError, "^invalid_annotations$"):
            self.run_metrics(pin="0" * 64)

    def test_malformed_boxes_and_json_reject(self):
        for boxes in (
            [BOX] * 65,
            [BOX] * 2,
            [[True, 0, 0.1, 0.1]],
            [[0, 0, 0, 0.1]],
            [[0.9, 0, 0.2, 0.1]],
            [[0, 0, float("nan"), 0.1]],
            [[0, 0, float("inf"), 0.1]],
            [[0, 0, -1, 0.1]],
            [[0, 0, 0.1]],
            "bad",
        ):
            doc = copy.deepcopy(self.doc)
            doc["samples"][0]["boxes"] = boxes
            with (
                self.subTest(boxes=boxes),
                self.assertRaisesRegex(ValueError, "^invalid_annotations$"),
            ):
                self.run_metrics(doc)
        for raw in (
            b"{}",
            b'{"version":1,"version":1}',
            b"[" * 9 + b"]" * 9,
            b"\xff",
            b" " * (2 * 1024 * 1024 + 1),
        ):
            with (
                self.subTest(size=len(raw)),
                self.assertRaisesRegex(ValueError, "^invalid_annotations$"),
            ):
                self.run_metrics(raw=raw)

    def test_complete_multiple_frames_match_by_id_not_annotation_order(self):
        row = dict(self.fixture.doc["samples"][2])
        source = b"original second source"
        row.update(id="second", source_sha256=hashlib.sha256(source).hexdigest())
        (self.fixture.root / row["source_sha256"]).write_bytes(source)
        self.fixture.doc["samples"].append(row)
        self.images.image(3, fixtures.pgm(210))
        self.doc["manifest_sha256"] = hashlib.sha256(self.fixture.raw()).hexdigest()
        self.doc["samples"].insert(
            0,
            {
                "sample_id": "second",
                "artifact_sha256": self.fixture.doc["samples"][3]["artifact_sha256"],
                "boxes": [[0, 0, 0.1, 0.1]],
            },
        )
        result = self.run_metrics()
        self.assertEqual(result["frames"], 2)
        self.assertEqual(
            result["metrics"],
            {
                "true_positives": 1,
                "false_positives": 0,
                "false_negatives": 1,
                "precision": 1.0,
                "recall": 0.5,
            },
        )
        self.doc["samples"][0]["boxes"] = [[0, 0, -1, 0.1]]
        with self.assertRaisesRegex(ValueError, "^invalid_annotations$"):
            self.run_metrics()

    def test_metrics_separate_declared_evidence_without_promoting_fixture_rights(self):
        # Both images are original synthetic fixtures. The recorded tag exercises
        # declared-metadata reporting only; it is not recorded accuracy evidence.
        provenance = copy.deepcopy(self.fixture.doc["provenance"][0])
        provenance.update(id="declared_recorded", evidence="recorded")
        self.fixture.doc["provenance"].append(provenance)
        row = dict(self.fixture.doc["samples"][2])
        row.update(id="second", provenance_id="declared_recorded")
        self.fixture.doc["samples"].append(row)
        self.images.image(3, fixtures.pgm(210))
        self.doc["manifest_sha256"] = hashlib.sha256(self.fixture.raw()).hexdigest()
        self.doc["samples"].append(
            {
                "sample_id": "second",
                "artifact_sha256": self.fixture.doc["samples"][3]["artifact_sha256"],
                "boxes": [[0, 0, 0.1, 0.1]],
            }
        )
        result = self.run_metrics()
        self.assertEqual(
            result["metrics_by_evidence"],
            {
                "synthetic": {
                    "frames": 1,
                    "true_positives": 1,
                    "false_positives": 0,
                    "false_negatives": 0,
                    "precision": 1.0,
                    "recall": 1.0,
                },
                "recorded": {
                    "frames": 1,
                    "true_positives": 0,
                    "false_positives": 0,
                    "false_negatives": 1,
                    "precision": None,
                    "recall": 0.0,
                },
            },
        )
        self.assertEqual(result["metrics"]["recall"], 0.5)
        self.assertFalse(result["qualified"])
        self.assertFalse(result["rights_verified"])
        self.fixture.doc["provenance"][1]["evidence"] = "synthetic"
        self.doc["manifest_sha256"] = hashlib.sha256(self.fixture.raw()).hexdigest()
        groups = self.run_metrics()["metrics_by_evidence"]
        self.assertEqual(groups["synthetic"]["frames"], 2)
        self.assertEqual(groups["synthetic"]["recall"], 0.5)
        self.assertEqual(
            groups["recorded"],
            {
                "frames": 0,
                "true_positives": 0,
                "false_positives": 0,
                "false_negatives": 0,
                "precision": None,
                "recall": None,
            },
        )

    def test_annotation_bytes_and_pin_are_both_required(self):
        for args in (
            {"annotations": json.dumps(self.doc).encode()},
            {"expected_annotations_sha256": "0" * 64},
        ):
            with (
                self.subTest(args=args),
                self.assertRaisesRegex(ValueError, "^invalid_annotations$"),
            ):
                self.images.run_baseline(**args)

    def test_unknown_matching_protocol_rejects_even_with_valid_digest(self):
        data = b"unknown protocol"
        digest = hashlib.sha256(data).hexdigest()
        (self.fixture.root / digest).write_bytes(data)
        self.fixture.doc["protocol_sha256"] = digest
        self.doc.update(
            protocol_sha256=digest, manifest_sha256=hashlib.sha256(self.fixture.raw()).hexdigest()
        )
        with self.assertRaisesRegex(ValueError, "^invalid_annotations$"):
            self.run_metrics()

    def test_matching_is_one_to_one_and_maximizes_cardinality_before_iou(self):
        api = importlib.import_module("aethron.evaluation.annotations")
        # First truth matches either; second matches only first proposal.
        truth = [[0, 0, 0.4, 0.2], [0, 0, 0.2, 0.2]]
        proposals = [[0, 0, 0.3, 0.2], [0.2, 0, 0.3, 0.2]]
        self.assertEqual(api.count_matches(truth, proposals), 2)
        self.assertEqual(api.count_matches([BOX], [BOX, BOX]), 1)
        self.assertEqual(api.count_matches([[0, 0, 1, 1]], [[0, 0, 0.3, 1]]), 1)
        self.assertEqual(api.count_matches([[0, 0, 1, 1]], [[0, 0, 0.2999, 1]]), 0)

    def test_cli_reports_metrics_or_rejects_without_partial_output(self):
        manifest = self.fixture.root.parent / "manifest.json"
        annotation = self.fixture.root.parent / "annotation.json"
        manifest.write_bytes(self.fixture.raw())
        raw = json.dumps(self.doc).encode()
        annotation.write_bytes(raw)
        command = [
            sys.executable,
            "-m",
            "aethron.evaluation.proposals",
            str(manifest),
            "--blob-dir",
            str(self.fixture.root),
            "--split",
            "test",
            "--manifest-sha256",
            self.doc["manifest_sha256"],
            "--protocol-sha256",
            self.doc["protocol_sha256"],
            "--annotations",
            str(annotation),
            "--annotations-sha256",
            hashlib.sha256(raw).hexdigest(),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["metrics"]["true_positives"], 1)
        annotation.write_bytes(b"private invalid annotations")
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "invalid_proposal_input")
