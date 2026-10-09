"""Original opaque candidate fixtures; structural checks grant no training or rights claims."""

import copy
import hashlib
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_dataset_artifacts as fixtures


def digest(data):
    return hashlib.sha256(data).hexdigest()


@unittest.skipIf(getattr(fixtures.DatasetArtifacts, "__unittest_skip__", False), "POSIX required")
class ModelCandidates(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.DatasetArtifacts()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.doc = {
            "version": 1,
            "task": "obstacle_proposals",
            "format": "opaque",
            "artifact_sha256": "",
            "preprocessing_sha256": "",
            "card_sha256": "",
            "rights_sha256": "",
            "protocol_sha256": self.fixture.doc["protocol_sha256"],
            "training_manifest_sha256": digest(self.fixture.raw()),
            "training_split": "train",
        }
        for key in ("artifact_sha256", "preprocessing_sha256", "card_sha256", "rights_sha256"):
            self.fixture.add_blob(self.doc, key)

    def api(self):
        self.assertIsNotNone(
            importlib.util.find_spec("aethron.evaluation.candidates"),
            "candidate validation API is missing",
        )
        return importlib.import_module("aethron.evaluation.candidates")

    def run_candidate(self, raw=None, manifest=None, verify=False, **changes):
        raw = json.dumps(self.doc).encode() if raw is None else raw
        manifest = self.fixture.raw() if manifest is None else manifest
        args = {
            "expected_candidate_sha256": digest(raw),
            "expected_manifest_sha256": digest(manifest),
            "expected_protocol_sha256": self.fixture.doc["protocol_sha256"],
        }
        args.update(changes)
        if verify:
            return self.api().verify_artifacts(raw, manifest, self.fixture.root, **args)
        return self.api().validate(raw, manifest, **args)

    def test_descriptor_binds_inputs_without_promoting_claims(self):
        report = self.run_candidate()
        self.assertEqual(report["candidate_sha256"], digest(json.dumps(self.doc).encode()))
        self.assertEqual(report["training_manifest_sha256"], digest(self.fixture.raw()))
        self.assertEqual(report["training_samples"], 1)
        self.assertEqual(report["training_split"], "train")
        self.assertEqual(report["artifact_sha256"], self.doc["artifact_sha256"])
        for key in (
            "qualified",
            "artifacts_verified",
            "rights_verified",
            "signatures_verified",
            "training_verified",
            "preprocessing_verified",
        ):
            self.assertIs(report[key], False)
        self.assertNotIn("samples", report)
        self.assertNotIn(str(self.fixture.root), json.dumps(report))
        # Descriptor-only mode does not touch even a missing artifact.
        (self.fixture.root / self.doc["artifact_sha256"]).unlink()
        self.assertEqual(self.run_candidate(), report)

    def test_unknown_fields_types_formats_tasks_and_held_out_training_reject(self):
        cases = []
        for key, value in (
            ("version", True),
            ("version", 2),
            ("task", "person_identity"),
            ("format", "pickle"),
            ("format", "onnx"),
            ("training_split", "test"),
            ("training_split", "validation"),
            ("training_split", ["train"]),
            ("qualified", True),
            ("private_owner_note", "secret"),
        ):
            row = dict(self.doc)
            row[key] = value
            cases.append(row)
        for key in self.doc:
            row = dict(self.doc)
            del row[key]
            cases.append(row)
        for key in (k for k in self.doc if k.endswith("sha256")):
            for value in (None, True, "A" * 64, "0" * 63, "../private/path"):
                row = dict(self.doc)
                row[key] = value
                cases.append(row)
        for row in cases:
            with (
                self.subTest(row=row),
                self.assertRaisesRegex(ValueError, "^invalid_model_candidate$"),
            ):
                self.run_candidate(raw=json.dumps(row).encode())

    def test_wrong_caller_pins_and_manifest_protocol_bindings_reject(self):
        for key in (
            "expected_candidate_sha256",
            "expected_manifest_sha256",
            "expected_protocol_sha256",
        ):
            for value in ("0" * 64, None, True):
                with (
                    self.subTest(key=key, value=value),
                    self.assertRaisesRegex(ValueError, "^invalid_model_candidate$"),
                ):
                    self.run_candidate(**{key: value})
        for key in ("training_manifest_sha256", "protocol_sha256"):
            row = dict(self.doc)
            row[key] = "0" * 64
            with self.assertRaisesRegex(ValueError, "^invalid_model_candidate$"):
                self.run_candidate(raw=json.dumps(row).encode())
        doc = copy.deepcopy(self.fixture.doc)
        doc["samples"][2]["source_sha256"] = doc["samples"][0]["artifact_sha256"]
        raw = json.dumps(doc).encode()
        self.doc["training_manifest_sha256"] = digest(raw)
        with self.assertRaisesRegex(ValueError, "^invalid_model_candidate$"):
            self.run_candidate(manifest=raw)

    def test_strict_json_and_candidate_size_bounds(self):
        valid = json.dumps(self.doc).encode()
        for raw in (
            b"[]",
            b"null",
            b"NaN",
            b"\xff",
            b"[" * 9 + b"]" * 9,
            valid[:-1] + b',"version":1}',
            b" " * 16385,
            bytearray(valid),
        ):
            with (
                self.subTest(raw=type(raw)),
                self.assertRaisesRegex(ValueError, "^invalid_model_candidate$"),
            ):
                self.run_candidate(raw=raw)
        padded = valid + b" " * (16384 - len(valid))
        self.assertEqual(self.run_candidate(raw=padded)["candidate_sha256"], digest(padded))
        with self.assertRaisesRegex(ValueError, "^invalid_model_candidate$"):
            self.run_candidate(raw=padded + b" ")

    def test_verifier_hashes_all_candidate_and_dataset_references_without_execution(self):
        report = self.run_candidate(verify=True)
        self.assertTrue(report["artifacts_verified"])
        self.assertEqual(report["verified_blob_reads"], 13)
        self.assertGreater(report["verified_bytes"], 0)
        for key in (
            "qualified",
            "rights_verified",
            "signatures_verified",
            "training_verified",
            "preprocessing_verified",
        ):
            self.assertIs(report[key], False)
        references = [
            self.doc[k]
            for k in ("artifact_sha256", "preprocessing_sha256", "card_sha256", "rights_sha256")
        ]
        references += [
            self.fixture.doc["samples"][2]["artifact_sha256"],
            self.doc["protocol_sha256"],
        ]
        for reference in references:
            path = self.fixture.root / reference
            saved = path.read_bytes()
            for content in (None, b"private tampered data"):
                path.unlink()
                if content is not None:
                    path.write_bytes(content)
                with (
                    self.subTest(reference=reference),
                    self.assertRaisesRegex(ValueError, "^invalid_model_candidate$"),
                ):
                    self.run_candidate(verify=True)
                path.write_bytes(saved)

    def test_verifier_enforces_combined_byte_budget_and_counts_shared_reads(self):
        api = self.api()
        report = self.run_candidate(verify=True)
        with patch.object(api, "MAX_TOTAL_BYTES", report["verified_bytes"]):
            self.assertEqual(self.run_candidate(verify=True), report)
        with patch.object(api, "MAX_TOTAL_BYTES", report["verified_bytes"] - 1):
            with self.assertRaisesRegex(ValueError, "^invalid_model_candidate$"):
                self.run_candidate(verify=True)
        self.doc["card_sha256"] = self.doc["rights_sha256"]
        self.assertEqual(self.run_candidate(verify=True)["verified_blob_reads"], 12)
        # A candidate role shared with the dataset is freshly checked and counted again.
        self.doc["preprocessing_sha256"] = self.doc["protocol_sha256"]
        self.assertEqual(self.run_candidate(verify=True)["verified_blob_reads"], 12)
        path = self.fixture.root / self.doc["artifact_sha256"]
        with path.open("wb") as stream:
            stream.truncate(64 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "^invalid_model_candidate$"):
            self.run_candidate(verify=True)

    def test_opaque_non_json_bytes_are_hashed_not_interpreted(self):
        payload = b"\x00\xffopaque candidate bytes; not an executable model contract"
        self.doc["artifact_sha256"] = digest(payload)
        (self.fixture.root / digest(payload)).write_bytes(payload)
        report = self.run_candidate(verify=True)
        self.assertTrue(report["artifacts_verified"])
        self.assertFalse(report["training_verified"])
        self.assertFalse(report["preprocessing_verified"])
        self.assertFalse(report["qualified"])

    def test_candidate_symlink_fifo_directory_and_root_aliases_reject(self):
        path = self.fixture.root / self.doc["artifact_sha256"]
        saved = path.read_bytes()
        outside = self.fixture.root.parent / "outside"
        outside.write_bytes(saved)
        for kind in ("symlink", "fifo", "directory"):
            path.unlink()
            if kind == "symlink":
                path.symlink_to(outside)
            elif kind == "fifo":
                os.mkfifo(path)
            else:
                path.mkdir()
            with (
                self.subTest(kind=kind),
                self.assertRaisesRegex(ValueError, "^invalid_model_candidate$"),
            ):
                self.run_candidate(verify=True)
            if kind == "directory":
                path.rmdir()
            else:
                path.unlink()
            path.write_bytes(saved)
        alias = self.fixture.root.parent / "alias"
        alias.symlink_to(self.fixture.root, target_is_directory=True)
        original = self.fixture.root
        for suffix in ("", "/", "/."):
            self.fixture.root = str(alias) + suffix
            with self.assertRaisesRegex(ValueError, "^invalid_model_candidate$"):
                self.run_candidate(verify=True)
        self.fixture.root = original

    def test_cli_regular_inputs_and_fixed_failure_without_partial_output(self):
        self.api()
        candidate = self.fixture.root.parent / "candidate.json"
        manifest = self.fixture.root.parent / "manifest.json"
        raw = json.dumps(self.doc).encode()
        candidate.write_bytes(raw)
        manifest.write_bytes(self.fixture.raw())
        command = [
            sys.executable,
            "-m",
            "aethron.evaluation.candidates",
            str(candidate),
            "--training-manifest",
            str(manifest),
            "--blob-dir",
            str(self.fixture.root),
            "--candidate-sha256",
            digest(raw),
            "--manifest-sha256",
            digest(self.fixture.raw()),
            "--protocol-sha256",
            self.doc["protocol_sha256"],
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), self.run_candidate(verify=True))
        for path in (candidate, manifest):
            original = path.read_bytes()
            for kind in ("malformed", "symlink", "fifo"):
                path.unlink()
                if kind == "malformed":
                    path.write_bytes(b"private bad input")
                elif kind == "symlink":
                    path.symlink_to(self.fixture.root / self.doc["artifact_sha256"])
                else:
                    os.mkfifo(path)
                result = subprocess.run(
                    command, capture_output=True, text=True, timeout=10, check=False
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.strip(), "invalid_model_candidate")
                path.unlink()
                path.write_bytes(original)
