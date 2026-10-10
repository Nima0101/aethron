"""Temporary Git roots only; no product child command executes."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify


class VerificationRoot(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.check_output(["git", *args], cwd=root, timeout=10)

    def reject(self, root):
        with patch.object(verify, "ROOT", root):
            with self.assertRaisesRegex(ValueError, "^invalid_verification_root$"):
                verify.tracked_files()
            with (
                patch.object(verify.subprocess, "run") as child,
                patch.object(
                    verify, "local_bytes", side_effect=AssertionError("unexpected read")
                ) as read,
            ):
                with self.assertRaisesRegex(ValueError, "^invalid_verification_root$"):
                    verify.run()
                child.assert_not_called()
                read.assert_not_called()

    def test_parent_repository_is_not_the_requested_root(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            self.git(parent, "init", "-q")
            nested = parent / "copied-checkout"
            nested.mkdir()
            (nested / "README.md").write_text("synthetic", encoding="utf-8")
            self.git(parent, "add", ".")
            self.assertEqual(
                self.git(nested, "ls-files", "--full-name", "-z"),
                b"copied-checkout/README.md\0",
            )
            self.reject(nested)

    def test_configured_worktree_cannot_shift_scan_root(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "checkout"
            root.mkdir()
            self.git(root, "init", "-q")
            self.git(root, "config", "core.worktree", str(parent))
            self.assertEqual(self.git(root, "rev-parse", "--show-prefix"), b"checkout/\n")
            self.reject(root)

    def test_bare_repository_is_not_a_working_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.git(root, "init", "--bare", "-q")
            self.reject(root)

    def test_independent_nested_repository_remains_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            self.git(parent, "init", "-q")
            root = parent / "independent"
            root.mkdir()
            self.git(root, "init", "-q")
            (root / "README.md").write_text("synthetic", encoding="utf-8")
            self.git(root, "add", ".")
            with patch.object(verify, "ROOT", root):
                self.assertEqual(verify.tracked_files(), {"README.md"})

    def test_root_probe_failure_prevents_inventory_and_children(self):
        error = subprocess.CalledProcessError(7, ["git", "rev-parse"])
        for operation in (verify.tracked_files, verify.run):
            with (
                self.subTest(operation=operation.__name__),
                patch.object(verify, "git_output", side_effect=error) as git,
                patch.object(verify.subprocess, "run") as child,
                patch.object(
                    verify, "local_bytes", side_effect=AssertionError("unexpected read")
                ) as read,
            ):
                with self.assertRaises(subprocess.CalledProcessError) as caught:
                    operation()
                self.assertIs(caught.exception, error)
                self.assertEqual(git.call_count, 1)
                child.assert_not_called()
                read.assert_not_called()
