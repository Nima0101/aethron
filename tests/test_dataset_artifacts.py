"""Local synthetic content-addressed blobs; hash matches do not grant rights."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_dataset_splits import manifest

from aethron.evaluation import splits


@unittest.skipUnless(
    os.open in os.supports_dir_fd
    and all(hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK", "mkfifo")),
    "POSIX artifact verification unavailable on this platform",
)
class DatasetArtifacts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "blobs"
        self.root.mkdir()
        self.doc = manifest()
        self.payloads = []
        self.add_blob(self.doc, "protocol_sha256")
        for row in self.doc["provenance"]:
            for key in ("card_sha256", "rights_sha256"):
                self.add_blob(row, key)
        for row in self.doc["samples"]:
            for key in ("source_sha256", "artifact_sha256"):
                self.add_blob(row, key)

    def add_blob(self, row, key):
        data = ("original fixture " + str(len(self.payloads))).encode()
        self.payloads.append(data)
        row[key] = hashlib.sha256(data).hexdigest()
        (self.root / row[key]).write_bytes(data)

    def raw(self):
        return json.dumps(self.doc).encode()

    def verify(self):
        return splits.verify_artifacts(self.raw(), self.root)

    def test_all_reference_roles_verified_without_rights_promotion(self):
        result = self.verify()
        self.assertTrue(result["artifacts_verified"])
        self.assertFalse(result["rights_verified"])
        self.assertFalse(result["qualified"])
        self.assertEqual(
            result["verified_references"],
            {"protocol": 1, "card": 1, "rights": 1, "source": 3, "artifact": 3},
        )
        self.assertEqual(result["verified_blobs"], 9)
        self.assertEqual(result["verified_bytes"], sum(map(len, self.payloads)))
        self.assertEqual(result["manifest_sha256"], hashlib.sha256(self.raw()).hexdigest())
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertFalse(splits.validate(self.raw())["artifacts_verified"])

    def test_missing_and_tampered_reference_in_each_role_rejected(self):
        refs = [
            (self.doc, "protocol_sha256"),
            (self.doc["provenance"][0], "card_sha256"),
            (self.doc["provenance"][0], "rights_sha256"),
            (self.doc["samples"][0], "source_sha256"),
            (self.doc["samples"][0], "artifact_sha256"),
        ]
        for row, key in refs:
            path = self.root / row[key]
            original = path.read_bytes()
            for tampered in (False, True):
                with self.subTest(key=key, tampered=tampered):
                    path.unlink()
                    if tampered:
                        path.write_bytes(b"tampered")
                    with self.assertRaisesRegex(ValueError, "^invalid_split_artifacts$"):
                        self.verify()
                    path.write_bytes(original)

    def test_symlink_directory_and_fifo_cannot_be_blob_inputs(self):
        path = self.root / self.doc["protocol_sha256"]
        original = path.read_bytes()
        outside = self.root.parent / "outside"
        outside.write_bytes(original)
        for kind in ("symlink", "directory", "fifo"):
            with self.subTest(kind=kind):
                path.unlink()
                if kind == "symlink":
                    path.symlink_to(outside)
                elif kind == "directory":
                    path.mkdir()
                else:
                    os.mkfifo(path)
                with self.assertRaisesRegex(ValueError, "^invalid_split_artifacts$"):
                    self.verify()
                if kind == "directory":
                    path.rmdir()
                else:
                    path.unlink()
                path.write_bytes(original)

    def test_root_symlink_is_rejected(self):
        link = self.root.parent / "alias"
        link.symlink_to(self.root, target_is_directory=True)
        for spelling in (str(link), str(link) + "/", str(link) + "/."):
            with self.subTest(spelling=spelling):
                with self.assertRaisesRegex(ValueError, "^invalid_split_artifacts$"):
                    splits.verify_artifacts(self.raw(), spelling)

    def test_blob_and_aggregate_limits_reject_and_exact_limit_passes(self):
        with patch.object(splits, "MAX_BLOB_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "^invalid_split_artifacts$"):
                self.verify()
        total = sum(map(len, self.payloads))
        with patch.object(splits, "MAX_TOTAL_BYTES", total - 1):
            with self.assertRaisesRegex(ValueError, "^invalid_split_artifacts$"):
                self.verify()
        with patch.object(splits, "MAX_TOTAL_BYTES", total):
            self.assertEqual(self.verify()["verified_bytes"], total)

    def test_shared_content_is_hashed_once_but_roles_still_count(self):
        self.doc["samples"][0]["source_sha256"] = self.doc["samples"][0]["artifact_sha256"]
        result = self.verify()
        self.assertEqual(result["verified_blobs"], 8)
        self.assertEqual(result["verified_references"]["source"], 3)
        self.assertEqual(result["verified_references"]["artifact"], 3)

    def test_cli_checks_blob_bytes_and_has_fixed_private_safe_error(self):
        path = self.root.parent / "manifest.json"
        path.write_bytes(self.raw())
        command = [
            sys.executable,
            "-m",
            "aethron.evaluation.splits",
            str(path),
            "--blob-dir",
            str(self.root),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["artifacts_verified"])
        (self.root / self.doc["protocol_sha256"]).write_bytes(b"private test content")
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr.strip(), "invalid_split_manifest")

    def test_blob_replacement_during_hash_is_rejected(self):
        first = sorted(self.root.iterdir())[0]
        original = first.read_bytes()
        read = os.read
        replaced = False

        def replace_then_read(fd, size):
            nonlocal replaced
            if not replaced:
                replaced = True
                first.rename(self.root.parent / "retired")
                first.write_bytes(original)
            return read(fd, size)

        with patch.object(splits.os, "read", side_effect=replace_then_read):
            with self.assertRaisesRegex(ValueError, "^invalid_split_artifacts$"):
                self.verify()

    def test_large_blob_is_streamed_in_bounded_reads(self):
        data = b"original synthetic bytes" * 6000
        digest = hashlib.sha256(data).hexdigest()
        (self.root / digest).write_bytes(data)
        self.doc["protocol_sha256"] = digest
        read = os.read
        sizes = []

        def bounded_read(fd, size):
            sizes.append(size)
            self.assertLessEqual(size, 65536)
            return read(fd, size)

        with patch.object(splits.os, "read", side_effect=bounded_read):
            result = self.verify()
        self.assertTrue(result["artifacts_verified"])
        self.assertGreaterEqual(sizes.count(65536), 2)

    def test_missing_descriptor_support_fails_closed(self):
        with patch.object(splits.os, "supports_dir_fd", set()):
            with self.assertRaisesRegex(ValueError, "^invalid_split_artifacts$"):
                self.verify()
