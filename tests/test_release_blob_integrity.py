"""Corrupt Git blob storage cannot certify a release under the original ID."""

import hashlib
import subprocess
import tempfile
import unittest
import zlib
from functools import partial
from pathlib import Path
from unittest.mock import patch

from scripts import release, reproduce


class ReleaseBlobIntegrity(unittest.TestCase):
    def git(self, root, *args, data=None):
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Release Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=" + str(root / "no-hooks"),
                *args,
            ],
            cwd=root,
            input=data,
            stderr=subprocess.PIPE,
            timeout=10,
        ).strip()

    def repository(self, root, algorithm):
        self.git(root, "init", "-q", "--object-format=" + algorithm)
        files = {
            "LICENSE": b"synthetic license\n",
            "NOTICE": b"synthetic notice\n",
            "aethron/models/rules.json": b"{}\n",
            "empty": b"",
            "binary": b"\0\xff\nblob 123\n",
            "duplicate": b"\0\xff\nblob 123\n",
        }
        for name, data in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.git(root, "add", ".")
        self.git(root, "commit", "-qm", "synthetic fixture")
        return self.git(root, "rev-parse", "HEAD").decode(), files

    def corrupt(self, root, revision, data):
        oid = self.git(root, "rev-parse", revision + ":binary").decode()
        # Only a disposable fixture's loose object is replaced. Git normally
        # makes these read-only, so enable this test's deliberate corruption.
        path = root / ".git" / "objects" / oid[:2] / oid[2:]
        path.chmod(0o600)
        path.write_bytes(zlib.compress(b"blob " + str(len(data)).encode() + b"\0" + data))
        # Independently demonstrate that ordinary Git batch reads return the
        # requested old ID with the changed bytes rather than checking its hash.
        response = self.git(root, "cat-file", "--batch", data=oid.encode() + b"\n")
        expected = oid.encode() + b" blob " + str(len(data)).encode() + b"\n" + data
        self.assertEqual(response, expected.rstrip())

    def test_corrupt_objects_reject_in_reader_builder_and_manifest_verifier(self):
        for algorithm in ("sha1", "sha256"):
            for data in (b"x" * 12, b"replacement of a different length\n", b""):
                with self.subTest(algorithm=algorithm, size=len(data)):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        revision, files = self.repository(root, algorithm)
                        self.corrupt(root, revision, data)
                        self.assertEqual(self.git(root, "status", "--porcelain"), b"")
                        files.update(binary=data, duplicate=data)
                        forged = {n: hashlib.sha256(v).hexdigest() for n, v in files.items()}
                        operations = (
                            partial(release.committed_blobs, revision, root=root),
                            partial(release.build, root / "output"),
                            partial(reproduce.validate_source_manifest, root, revision, forged),
                        )
                        for index, operation in enumerate(operations):
                            with self.subTest(operation=index), patch.object(release, "ROOT", root):
                                with self.assertRaisesRegex(
                                    ValueError, "^release_blob_hash_mismatch$"
                                ):
                                    operation()
                                self.assertFalse((root / "output").exists())

    def test_intact_empty_binary_and_shared_objects_remain_supported(self):
        for algorithm in ("sha1", "sha256"):
            with self.subTest(algorithm=algorithm), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                revision, files = self.repository(root, algorithm)
                self.assertEqual(release.committed_blobs(revision, root=root), files)
                with patch.object(release, "ROOT", root):
                    self.assertEqual(release.build(root / "output"), revision)
                manifest = {n: hashlib.sha256(v).hexdigest() for n, v in files.items()}
                reproduce.validate_source_manifest(root, revision, manifest)


if __name__ == "__main__":
    unittest.main()
