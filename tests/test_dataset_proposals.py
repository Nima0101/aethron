"""Original PGM fixtures through verified loading and the real pixel baseline."""

import hashlib
import importlib
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_dataset_artifacts as fixtures

from aethron.evaluation.synthetic import generate


def pgm(background, spot=False):
    pixels = bytearray([background] * 64)
    if spot:
        for index in (27, 28, 35, 36):
            pixels[index] = 0
    return b"P5\n8 8\n255\n" + bytes(pixels)


@unittest.skipIf(getattr(fixtures.DatasetArtifacts, "__unittest_skip__", False), "POSIX required")
class DatasetProposals(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DatasetArtifacts()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        for i, data in enumerate((pgm(180), pgm(200), pgm(220, True))):
            self.image(i, data)

    def image(self, index, data):
        digest = hashlib.sha256(data).hexdigest()
        (self.fixture.root / digest).write_bytes(data)
        self.fixture.doc["samples"][index]["artifact_sha256"] = digest

    def run_baseline(self, split="test", **changes):
        api = importlib.import_module("aethron.evaluation.proposals")
        raw = self.fixture.raw()
        args = {
            "expected_manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "expected_protocol_sha256": self.fixture.doc["protocol_sha256"],
        }
        args.update(changes)
        return api.run(raw, self.fixture.root, split, **args)

    def test_actual_pixels_produce_only_bound_aggregate_counts(self):
        result = self.run_baseline()
        self.assertEqual(result["frames"], 1)
        self.assertEqual(result["frames_with_proposals"], 1)
        self.assertEqual(result["proposal_count"], 1)
        self.assertEqual(result["evidence_counts"], {"synthetic": 1, "recorded": 0})
        self.assertEqual(result["manifest_sha256"], hashlib.sha256(self.fixture.raw()).hexdigest())
        self.assertEqual(result["protocol_sha256"], self.fixture.doc["protocol_sha256"])
        self.assertEqual(result["split"], "test")
        self.assertEqual(result["training"], "none")
        self.assertFalse(result["qualified"])
        self.assertFalse(result["rights_verified"])
        self.assertFalse(result["accuracy_evaluated"])
        self.assertNotIn("box", json.dumps(result))
        self.assertNotIn(str(self.fixture.root), json.dumps(result))
        self.assertEqual(self.run_baseline("train")["proposal_count"], 0)
        self.assertEqual(result, self.run_baseline())

    def test_tampered_blob_and_wrong_pins_rejected(self):
        with self.assertRaisesRegex(ValueError, "^invalid_split_selection$"):
            self.run_baseline(expected_protocol_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "^invalid_split_selection$"):
            self.run_baseline(expected_manifest_sha256="0" * 64)
        path = self.fixture.root / self.fixture.doc["samples"][2]["artifact_sha256"]
        path.write_bytes(pgm(100))
        with self.assertRaisesRegex(ValueError, "^invalid_split_artifacts$"):
            self.run_baseline()

    def test_malformed_selected_pgm_rejected(self):
        for data in (b"private invalid bytes", b"P5\n8 8\n255\nshort", b"P5\n641 1\n255\n"):
            with self.subTest(data=data):
                self.image(2, data)
                with self.assertRaisesRegex(ValueError, "^invalid_proposal_input$"):
                    self.run_baseline()

    def test_runner_budgets_reject_before_detection_and_accept_exact_boundary(self):
        api = importlib.import_module("aethron.evaluation.proposals")
        for limit in ("MAX_FRAMES", "MAX_PIXELS"):
            with patch.object(api, limit, 0):
                with self.assertRaisesRegex(ValueError, "^invalid_proposal_input$"):
                    self.run_baseline()
        with patch.object(api, "MAX_FRAMES", 1), patch.object(api, "MAX_PIXELS", 64):
            self.assertEqual(self.run_baseline()["proposal_count"], 1)

    def test_cli_has_no_partial_report_when_later_image_is_invalid(self):
        row = dict(self.fixture.doc["samples"][2])
        row.update(id="later", source_sha256=hashlib.sha256(b"later source").hexdigest())
        self.fixture.doc["samples"].append(row)
        (self.fixture.root / row["source_sha256"]).write_bytes(b"later source")
        self.image(3, b"private invalid PGM")
        raw = self.fixture.raw()
        path = self.fixture.root.parent / "manifest.json"
        path.write_bytes(raw)
        command = [
            sys.executable,
            "-m",
            "aethron.evaluation.proposals",
            str(path),
            "--blob-dir",
            str(self.fixture.root),
            "--split",
            "test",
            "--manifest-sha256",
            hashlib.sha256(raw).hexdigest(),
            "--protocol-sha256",
            self.fixture.doc["protocol_sha256"],
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "invalid_proposal_input")
        self.image(3, pgm(210))
        raw = self.fixture.raw()
        path.write_bytes(raw)
        command[command.index("--manifest-sha256") + 1] = hashlib.sha256(raw).hexdigest()
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["frames"], 2)
        self.assertEqual(json.loads(result.stdout)["proposal_count"], 1)

    def test_cli_rejects_nonregular_linked_and_oversized_documents(self):
        root = self.fixture.root.parent / "generated"
        pins = generate(root)
        command = [
            sys.executable,
            "-m",
            "aethron.evaluation.proposals",
            str(root / "manifest.json"),
            "--blob-dir",
            str(root / "blobs"),
            "--split",
            "test",
            "--manifest-sha256",
            pins["manifest_sha256"],
            "--protocol-sha256",
            pins["protocol_sha256"],
            "--annotations",
            str(root / "annotations-test.json"),
            "--annotations-sha256",
            pins["annotations_sha256"]["test"],
        ]
        for name, index in (("manifest.json", 3), ("annotations-test.json", 13)):
            for kind in ("fifo", "symlink", "directory", "oversized"):
                with self.subTest(document=name, kind=kind):
                    path = root / (name + "." + kind)
                    if kind == "fifo":
                        os.mkfifo(path)
                    elif kind == "symlink":
                        path.symlink_to(root / name)
                    elif kind == "directory":
                        path.mkdir()
                    else:
                        path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
                    changed = list(command)
                    changed[index] = str(path)
                    result = subprocess.run(
                        changed, capture_output=True, text=True, timeout=10, check=False
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(result.stderr.strip(), "invalid_proposal_input")
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["metrics"]["true_positives"], 1)
