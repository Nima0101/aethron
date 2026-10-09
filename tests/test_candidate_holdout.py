"""Synthetic declarations exercise separation only; no rights or model claims."""

import copy
import hashlib
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_dataset_splits import digest, manifest

from aethron.evaluation.splits import _filesystem_supported


def encode(doc):
    return json.dumps(doc, sort_keys=True).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


class CandidateHoldout(unittest.TestCase):
    def setUp(self):
        self.training = manifest()
        self.evaluation = manifest()
        for row in self.evaluation["samples"]:
            for key in ("artifact_sha256", "source_sha256", "session_sha256"):
                row[key] = digest("evaluation " + row[key])
        self.candidate = {
            "version": 1,
            "task": "obstacle_proposals",
            "format": "opaque",
            "artifact_sha256": digest("opaque model"),
            "preprocessing_sha256": digest("preprocessing"),
            "card_sha256": digest("model card"),
            "rights_sha256": digest("model rights"),
            "protocol_sha256": self.training["protocol_sha256"],
            "training_manifest_sha256": sha(encode(self.training)),
            "training_split": "train",
        }

    def api(self):
        self.assertIsNotNone(
            importlib.util.find_spec("aethron.evaluation.holdout"),
            "candidate held-out declaration gate is missing",
        )
        return importlib.import_module("aethron.evaluation.holdout")

    def pins(self):
        return {
            "expected_candidate_sha256": sha(encode(self.candidate)),
            "expected_manifest_sha256": sha(encode(self.training)),
            "expected_evaluation_manifest_sha256": sha(encode(self.evaluation)),
            "expected_protocol_sha256": self.training["protocol_sha256"],
        }

    def run_gate(self, **changes):
        pins = self.pins()
        pins.update(changes)
        return self.api().validate(
            encode(self.candidate), encode(self.training), encode(self.evaluation), **pins
        )

    def test_disjoint_test_declarations_bind_all_inputs_without_promoting_claims(self):
        report = self.run_gate()
        self.assertEqual(report["candidate_sha256"], self.pins()["expected_candidate_sha256"])
        self.assertEqual(report["training_manifest_sha256"], sha(encode(self.training)))
        self.assertEqual(report["evaluation_manifest_sha256"], sha(encode(self.evaluation)))
        self.assertEqual(report["protocol_sha256"], self.training["protocol_sha256"])
        self.assertEqual(report["development_samples"], 2)
        self.assertEqual(report["evaluation_samples"], 1)
        self.assertTrue(report["declared_test_separation"])
        for key in ("artifacts_verified", "rights_verified", "training_verified", "qualified"):
            self.assertIs(report[key], False)
        self.assertNotIn("samples", report)
        self.assertNotIn("original synthetic fixtures", json.dumps(report))

    def test_test_overlap_with_training_or_validation_rejects_all_content_aliases(self):
        original = copy.deepcopy(self.evaluation)
        pairs = [
            (left, right)
            for left in ("source_sha256", "artifact_sha256")
            for right in ("source_sha256", "artifact_sha256")
        ] + [("session_sha256", "session_sha256")]
        for split_index in (0, 1):
            for left, right in pairs:
                self.evaluation = copy.deepcopy(original)
                self.evaluation["samples"][2][right] = self.training["samples"][split_index][left]
                with self.subTest(split=split_index, left=left, right=right):
                    with self.assertRaisesRegex(ValueError, "^invalid_candidate_holdout$"):
                        self.run_gate()

    def test_same_manifest_and_shared_test_only_are_permitted(self):
        self.evaluation = copy.deepcopy(self.training)
        self.assertTrue(self.run_gate()["declared_test_separation"])

    def test_every_caller_pin_is_required_and_exact(self):
        for key in self.pins():
            for value in (None, True, "A" * 64, "0" * 64):
                with self.subTest(key=key, value=value):
                    with self.assertRaisesRegex(ValueError, "^invalid_candidate_holdout$"):
                        self.run_gate(**{key: value})

    def test_protocol_disagreement_and_invalid_candidate_reject(self):
        self.evaluation["protocol_sha256"] = digest("another protocol")
        with self.assertRaisesRegex(ValueError, "^invalid_candidate_holdout$"):
            self.run_gate()
        self.evaluation["protocol_sha256"] = self.training["protocol_sha256"]
        self.candidate["training_split"] = "test"
        with self.assertRaisesRegex(ValueError, "^invalid_candidate_holdout$"):
            self.run_gate()

    def test_both_manifests_must_be_valid_even_outside_compared_splits(self):
        for which in ("training", "evaluation"):
            original = copy.deepcopy(getattr(self, which))
            doc = getattr(self, which)
            doc["samples"][1]["session_sha256"] = doc["samples"][0]["session_sha256"]
            # Bind the malformed training declaration so the split check must reject it.
            self.candidate["training_manifest_sha256"] = sha(encode(self.training))
            with self.subTest(which=which):
                with self.assertRaisesRegex(ValueError, "^invalid_candidate_holdout$"):
                    self.run_gate()
            setattr(self, which, original)
            self.candidate["training_manifest_sha256"] = sha(encode(self.training))

    def test_malformed_bounded_documents_have_fixed_errors(self):
        api = self.api()
        good = [encode(self.candidate), encode(self.training), encode(self.evaluation)]
        for position in range(3):
            for bad in (
                b"null",
                b"NaN",
                b"\xff",
                b"[" * 9 + b"]" * 9,
                b" " * (2 * 1024 * 1024 + 1),
                good[position][:-1] + b',"version":1}',
                bytearray(good[position]),
            ):
                inputs = good.copy()
                inputs[position] = bad
                pins = self.pins()
                key = (
                    "expected_candidate_sha256",
                    "expected_manifest_sha256",
                    "expected_evaluation_manifest_sha256",
                )[position]
                pins[key] = sha(bad)
                with self.subTest(position=position, kind=type(bad)):
                    with self.assertRaisesRegex(ValueError, "^invalid_candidate_holdout$"):
                        api.validate(*inputs, **pins)

    def test_ordering_and_renamed_metadata_cannot_hide_overlap(self):
        self.evaluation["samples"].reverse()
        self.evaluation["provenance"][0]["id"] = "renamed"
        for row in self.evaluation["samples"]:
            row["provenance_id"] = "renamed"
            row["id"] = "renamed_" + row["id"]
        self.assertTrue(self.run_gate()["declared_test_separation"])
        self.evaluation["samples"][0]["source_sha256"] = self.training["samples"][1][
            "artifact_sha256"
        ]
        with self.assertRaisesRegex(ValueError, "^invalid_candidate_holdout$"):
            self.run_gate()

    @unittest.skipUnless(_filesystem_supported(), "POSIX required")
    def test_cli_is_deterministic_and_rejects_unsafe_inputs_without_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = [root / name for name in ("candidate", "training", "evaluation")]
            for path, doc in zip(paths, (self.candidate, self.training, self.evaluation)):
                path.write_bytes(encode(doc))
            command = [
                sys.executable,
                "-m",
                "aethron.evaluation.holdout",
                str(paths[0]),
                "--training-manifest",
                str(paths[1]),
                "--evaluation-manifest",
                str(paths[2]),
            ]
            for key, value in self.pins().items():
                command.extend(["--" + key.removeprefix("expected_").replace("_", "-"), value])

            def run():
                return subprocess.run(command, capture_output=True, timeout=10, check=False)

            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), self.run_gate())
            self.assertEqual(run().stdout, result.stdout)
            for path in paths:
                saved = path.read_bytes()
                for kind in ("invalid", "missing", "directory", "symlink", "fifo"):
                    path.unlink()
                    if kind == "invalid":
                        path.write_bytes(b"private invalid fixture")
                    elif kind == "directory":
                        path.mkdir()
                    elif kind == "symlink":
                        path.symlink_to(root / "missing")
                    elif kind == "fifo":
                        os.mkfifo(path)
                    result = run()
                    with self.subTest(path=path.name, kind=kind):
                        self.assertEqual(result.returncode, 2)
                        self.assertEqual(result.stdout, b"")
                        self.assertEqual(result.stderr, b"invalid_candidate_holdout\n")
                    if kind == "directory":
                        path.rmdir()
                    elif kind != "missing":
                        path.unlink()
                    path.write_bytes(saved)


if __name__ == "__main__":
    unittest.main()
