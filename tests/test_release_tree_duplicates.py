"""Ambiguous Git trees must not become apparently complete release manifests."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import release


class ReleaseTreeDuplicates(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.git("init", "-q")
        self.first = self.git("hash-object", "-w", "--stdin", data=b"first payload\n")
        self.second = self.git("hash-object", "-w", "--stdin", data=b"second payload\n")

    def git(self, *args, data=None):
        return subprocess.check_output(
            ["git", *args], cwd=self.root, input=data, stderr=subprocess.PIPE, timeout=10
        ).strip()

    def tree(self, *entries):
        return self.git("mktree", "-z", data=b"\0".join(entries) + b"\0")

    def blob(self, name, oid=None):
        return b"100644 blob " + (self.first if oid is None else oid) + b"\t" + name

    def directory(self, name, tree):
        return b"040000 tree " + tree + b"\t" + name

    def assert_rejected(self, tree):
        execute = subprocess.check_output
        calls = []

        def git(args, **kwargs):
            calls.append(args)
            return execute(args, **kwargs)

        with patch.object(release.subprocess, "check_output", side_effect=git):
            with self.assertRaisesRegex(ValueError, "release_duplicate_tree_path"):
                release.committed_blobs(tree.decode(), root=self.root)
        self.assertFalse(any("cat-file" in args for args in calls))

    def test_duplicate_files_reject_before_payload_reads(self):
        for objects in ((self.first, self.second), (self.second, self.first), (self.first,) * 2):
            for nested in (False, True):
                with self.subTest(objects=objects, nested=nested):
                    tree = self.tree(*(self.blob(b"payload", oid) for oid in objects))
                    if nested:
                        tree = self.tree(self.directory(b"source", tree))
                    self.assert_rejected(tree)

    def test_duplicate_directories_with_distinct_children_reject(self):
        children = [self.tree(self.blob(name)) for name in (b"first", b"second")]
        self.assert_rejected(self.tree(*(self.directory(b"source", t) for t in children)))

    def test_file_directory_collision_rejects(self):
        child = self.tree(self.blob(b"payload"))
        self.assert_rejected(self.tree(self.blob(b"source"), self.directory(b"source", child)))

    def test_distinct_paths_may_share_blobs_and_subtrees(self):
        child = self.tree(self.blob(b"first"), self.blob(b"second"))
        tree = self.tree(*(self.directory(name, child) for name in (b"a", b"b")))
        self.assertEqual(
            release.committed_blobs(tree.decode(), root=self.root),
            {
                f"{directory}/{name}": b"first payload\n"
                for directory in ("a", "b")
                for name in ("first", "second")
            },
        )


if __name__ == "__main__":
    unittest.main()
