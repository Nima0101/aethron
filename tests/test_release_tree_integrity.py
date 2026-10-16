"""Release provenance must reject corrupt nested directory-tree storage."""

import hashlib
import io
import subprocess
import tempfile
import unittest
import zlib
from functools import partial
from pathlib import Path
from unittest.mock import patch

from scripts import release, reproduce
from tests import test_release_blob_integrity as fixtures


class ReleaseTreeIntegrity(unittest.TestCase):
    git = fixtures.ReleaseBlobIntegrity.git
    repository = fixtures.ReleaseBlobIntegrity.repository

    def test_corrupt_nested_trees_cannot_certify_original_revision(self):
        for algorithm in ("sha1", "sha256"):
            for location in ("aethron", "aethron/models"):
                with self.subTest(algorithm=algorithm, location=location):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        revision, files = self.repository(root, algorithm)
                        expression = revision + ":" + location
                        oid = self.git(root, "rev-parse", expression).decode()
                        kind = "tree"
                        # Preserve parseable object framing and all referenced blobs.
                        raw = subprocess.check_output(
                            ["git", "cat-file", kind, oid], cwd=root, timeout=10
                        )
                        # Git also accepts the noncanonical leading zero on a
                        # directory mode. Both mutations preserve blob contents.
                        # File permissions are normalized in release artifacts.
                        changed = (
                            raw.replace(b"40000 ", b"040000 ", 1)
                            if location == "aethron"
                            else raw.replace(b"100644 ", b"100755 ", 1)
                        )
                        self.assertNotEqual(raw, changed)
                        path = root / ".git" / "objects" / oid[:2] / oid[2:]
                        path.chmod(0o600)
                        path.write_bytes(
                            zlib.compress(
                                kind.encode() + b" " + str(len(changed)).encode() + b"\0" + changed
                            )
                        )
                        # Real Git still reports the old ID and returns the altered
                        # payload. The ordinary checkout check also reports clean.
                        self.assertEqual(self.git(root, "status", "--porcelain"), b"")
                        manifest = {n: hashlib.sha256(v).hexdigest() for n, v in files.items()}
                        operations = (
                            partial(release.committed_blobs, revision, root=root),
                            partial(release.build, root / "output"),
                            partial(reproduce.validate_source_manifest, root, revision, manifest),
                        )
                        for index, operation in enumerate(operations):
                            with self.subTest(operation=index), patch.object(release, "ROOT", root):
                                with self.assertRaisesRegex(
                                    ValueError, "^release_tree_hash_mismatch$"
                                ):
                                    operation()
                                self.assertFalse((root / "output").exists())

    def test_intact_commit_tree_and_symbolic_revision_are_supported(self):
        for algorithm in ("sha1", "sha256"):
            with self.subTest(algorithm=algorithm), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                revision, files = self.repository(root, algorithm)
                tree = self.git(root, "rev-parse", revision + "^{tree}").decode()
                for source in (revision, tree, "HEAD"):
                    self.assertEqual(release.committed_blobs(source, root=root), files)
                # Packed objects use the same raw-object digest convention.
                self.git(root, "gc", "--quiet")
                self.assertEqual(release.committed_blobs(revision, root=root), files)

    def test_shared_empty_subtrees_are_verified_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.git(root, "init", "-q")
            empty = self.git(root, "mktree", data=b"")
            tree = self.git(
                root,
                "mktree",
                data=b"040000 tree " + empty + b"\ta\n040000 tree " + empty + b"\tb\n",
            )
            execute = subprocess.check_output
            with patch.object(release.subprocess, "check_output", wraps=execute) as calls:
                self.assertEqual(release.committed_blobs(tree.decode(), root=root), {})
            requests = [c.kwargs["input"] for c in calls.call_args_list if "input" in c.kwargs]
            self.assertEqual(requests, [empty + b"\n"])

    def test_incomplete_or_mismatched_tree_batch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            revision, _ = self.repository(root, "sha1")
            execute = subprocess.check_output
            for defect in ("missing", "short-data", "separator", "type", "oid", "size"):
                with self.subTest(defect=defect):

                    def damaged(args, defect=defect, **kwargs):
                        result = execute(args, **kwargs)
                        if args[2] != "cat-file":
                            return result
                        stream = io.BytesIO(result)
                        while True:
                            start = stream.tell()
                            oid, kind, size = stream.readline().split()
                            data_start = stream.tell()
                            end = data_start + int(size)
                            if kind == b"tree":
                                break
                            stream.seek(end + 1)
                        if defect == "missing":
                            return result[:start]
                        if defect == "short-data":
                            return result[: end - 1]
                        if defect == "separator":
                            return result[:end] + b"!" + result[end + 1 :]
                        header = result[start:data_start]
                        if defect == "type":
                            header = header.replace(b" tree ", b" blob ")
                        elif defect == "oid":
                            header = b"0" * len(oid) + header[len(oid) :]
                        else:
                            header = oid + b" tree -1\n"
                        return result[:start] + header + result[data_start:]

                    with patch.object(release.subprocess, "check_output", side_effect=damaged):
                        with self.assertRaisesRegex(ValueError, "^release_tree_response_invalid$"):
                            release.committed_blobs(revision, root=root)


if __name__ == "__main__":
    unittest.main()
