"""Original synthetic descriptors; no third-party data or rights claims."""

import copy
import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aethron.evaluation.splits import _filesystem_supported


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def manifest():
    return {
        "version": 1,
        "protocol_sha256": digest("original synthetic protocol"),
        "provenance": [
            {
                "id": "fixture",
                "source": "original synthetic fixtures",
                "origin": "AETHRON tests",
                "license": "GPL-3.0-only",
                "evidence": "synthetic",
                "rights_sha256": digest("fixture rights record"),
                "card_sha256": digest("fixture card"),
                "allowed_splits": ["train", "validation", "test"],
            }
        ],
        "samples": [
            {
                "id": split,
                "split": split,
                "session_sha256": digest(split + " session"),
                "artifact_sha256": digest(split + " artifact"),
                "source_sha256": digest(split + " source"),
                "provenance_id": "fixture",
            }
            for split in ("train", "validation", "test")
        ],
    }


class DatasetSplits(unittest.TestCase):
    def validate(self, doc):
        return importlib.import_module("aethron.evaluation.splits").validate(
            json.dumps(doc).encode()
        )

    def reject(self, doc):
        with self.assertRaisesRegex(ValueError, "^invalid_split_manifest$"):
            self.validate(doc)

    def test_disjoint_manifest_reports_counts_without_qualification(self):
        doc = manifest()
        result = self.validate(doc)
        self.assertEqual(result["counts"], {"train": 1, "validation": 1, "test": 1})
        self.assertEqual(
            result["manifest_sha256"], hashlib.sha256(json.dumps(doc).encode()).hexdigest()
        )
        self.assertEqual(result["protocol_sha256"], doc["protocol_sha256"])
        self.assertFalse(result["qualified"])
        self.assertFalse(result["artifacts_verified"])
        self.assertFalse(result["rights_verified"])
        self.assertNotIn("samples", result)

    def test_cross_split_raw_derived_and_session_leakage_rejected(self):
        for left, right in (
            ("artifact_sha256", "artifact_sha256"),
            ("source_sha256", "source_sha256"),
            ("source_sha256", "artifact_sha256"),
            ("artifact_sha256", "source_sha256"),
            ("session_sha256", "session_sha256"),
        ):
            with self.subTest(left=left, right=right):
                doc = manifest()
                doc["samples"][1][right] = doc["samples"][0][left]
                self.reject(doc)

    def test_shared_session_and_source_allowed_only_inside_one_split(self):
        doc = manifest()
        row = copy.deepcopy(doc["samples"][0])
        row.update(id="augmentation", artifact_sha256=digest("augmented"))
        doc["samples"].append(row)
        self.assertEqual(self.validate(doc)["counts"]["train"], 2)
        row["artifact_sha256"] = doc["samples"][0]["artifact_sha256"]
        self.reject(doc)

    def test_missing_unknown_and_restricted_provenance_rejected(self):
        for cause in ("missing", "unknown", "restricted", "unused", "duplicate"):
            with self.subTest(cause=cause):
                doc = manifest()
                if cause == "missing":
                    del doc["provenance"][0]["rights_sha256"]
                elif cause == "unknown":
                    doc["samples"][0]["provenance_id"] = "unknown"
                elif cause == "restricted":
                    doc["provenance"][0]["allowed_splits"] = ["test"]
                elif cause == "unused":
                    row = copy.deepcopy(doc["provenance"][0])
                    row["id"] = "unused"
                    doc["provenance"].append(row)
                else:
                    doc["provenance"].append(copy.deepcopy(doc["provenance"][0]))
                self.reject(doc)

    def test_invalid_membership_and_closed_fields_rejected(self):
        for cause in (
            "split",
            "duplicate_id",
            "no_test",
            "empty",
            "bool_version",
            "unknown_field",
            "digest",
            "license",
        ):
            with self.subTest(cause=cause):
                doc = manifest()
                if cause == "split":
                    doc["samples"][0]["split"] = "training"
                elif cause == "duplicate_id":
                    doc["samples"][1]["id"] = "train"
                elif cause == "no_test":
                    doc["samples"].pop()
                elif cause == "empty":
                    doc["samples"] = []
                elif cause == "bool_version":
                    doc["version"] = True
                elif cause == "unknown_field":
                    doc["samples"][0]["person_id"] = "private"
                elif cause == "digest":
                    doc["samples"][0]["source_sha256"] = "A" * 64
                else:
                    doc["provenance"][0]["license"] = " "
                self.reject(doc)

    def test_bounded_strict_json_rejects_duplicates_depth_and_nonfinite(self):
        api = importlib.import_module("aethron.evaluation.splits")
        raw = json.dumps(manifest()).encode()
        for data in (
            raw.replace(b'"version": 1', b'"version": 1, "version": 1'),
            b"[" * 10 + b"]" * 10,
            b"NaN",
            b"\xff",
            b" " * (2 * 1024 * 1024 + 1),
        ):
            with self.subTest(prefix=data[:20]):
                with self.assertRaisesRegex(ValueError, "^invalid_split_manifest$"):
                    api.validate(data)

    def test_cli_has_fixed_error_and_does_not_echo_private_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            path.write_text(json.dumps(manifest()))
            command = [sys.executable, "-m", "aethron.evaluation.splits", str(path)]
            ok = subprocess.run(command, capture_output=True, text=True, check=False)
            if _filesystem_supported():
                self.assertEqual(ok.returncode, 0, ok.stderr)
                self.assertEqual(json.loads(ok.stdout)["counts"]["test"], 1)
            else:
                self.assertEqual(ok.returncode, 2)
                self.assertEqual(ok.stdout, "")
                self.assertEqual(ok.stderr.strip(), "invalid_split_manifest")
            path.write_text('{"private": "secret-fixture"}')
            bad = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(bad.stdout, "")
            self.assertEqual(bad.stderr.strip(), "invalid_split_manifest")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW") and hasattr(os, "mkfifo"), "POSIX required")
    def test_cli_rejects_fifo_symlink_and_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            regular = root / "manifest.json"
            regular.write_text(json.dumps(manifest()))
            for kind in ("fifo", "symlink", "directory"):
                with self.subTest(kind=kind):
                    path = root / kind
                    if kind == "fifo":
                        os.mkfifo(path)
                    elif kind == "symlink":
                        path.symlink_to(regular)
                    else:
                        path.mkdir()
                    result = subprocess.run(
                        [sys.executable, "-m", "aethron.evaluation.splits", str(path)],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(result.stderr.strip(), "invalid_split_manifest")

    @unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "POSIX required")
    def test_cli_accepts_exact_document_limit_and_rejects_one_extra_byte(self):
        raw = json.dumps(manifest()).encode().ljust(2 * 1024 * 1024, b" ")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            command = [sys.executable, "-m", "aethron.evaluation.splits", str(path)]
            path.write_bytes(raw)
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=10, check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout)["manifest_sha256"], hashlib.sha256(raw).hexdigest()
            )
            path.write_bytes(raw + b" ")
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=10, check=False
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr.strip(), "invalid_split_manifest")

    def test_collection_bounds_and_nonstring_metadata_fail_closed(self):
        for cause in ("samples", "provenance", "source", "allowed", "session"):
            with self.subTest(cause=cause):
                doc = manifest()
                if cause == "samples":
                    doc["samples"] *= 1366
                elif cause == "provenance":
                    doc["provenance"] *= 129
                elif cause == "source":
                    doc["provenance"][0]["source"] = []
                elif cause == "allowed":
                    doc["provenance"][0]["allowed_splits"] = [["test"]]
                else:
                    doc["samples"][0]["session_sha256"] = None
                self.reject(doc)

    def test_renamed_provenance_cannot_hide_cross_split_content(self):
        doc = manifest()
        other = copy.deepcopy(doc["provenance"][0])
        other["id"] = "second_source"
        doc["provenance"].append(other)
        doc["samples"][1]["provenance_id"] = "second_source"
        doc["samples"][1]["source_sha256"] = doc["samples"][0]["source_sha256"]
        self.reject(doc)
