"""Synthetic Git context checks; product children are never executed."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import public_links, verify
from tests import test_verify_static as static_checks

OVERRIDES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
)


class GitContext(unittest.TestCase):
    fixture = static_checks.StaticCheckClaims.fixture

    def test_inventory_rejects_overrides_before_git(self):
        for name in OVERRIDES:
            for value in ("", "synthetic-private-value"):
                with (
                    self.subTest(name=name, value=value),
                    patch.dict(os.environ, {name: value}),
                    patch.object(verify, "git_output", return_value=b"") as git,
                ):
                    with self.assertRaisesRegex(ValueError, "^git_repository_override$"):
                        verify.tracked_files()
                    git.assert_not_called()

    def test_verifier_rejects_before_children_or_file_reads(self):
        for name in OVERRIDES:
            with self.subTest(name=name), self.fixture("value = 1") as (output, calls):
                with (
                    patch.dict(os.environ, {name: "synthetic-private-value"}),
                    patch.object(verify, "local_bytes", wraps=verify.local_bytes) as read,
                ):
                    with self.assertRaisesRegex(ValueError, "^git_repository_override$"):
                        verify.run()
                    read.assert_not_called()
                self.assertEqual(calls, [])
                self.assertEqual(output.getvalue(), "")

    def test_public_tree_rejects_overrides_before_git(self):
        for name in OVERRIDES:
            for value in ("", "synthetic-private-value"):
                with (
                    self.subTest(name=name, value=value),
                    patch.dict(os.environ, {name: value}),
                    patch.object(public_links, "git_output", return_value=b"") as git,
                ):
                    with self.assertRaisesRegex(ValueError, "^git_repository_override$"):
                        public_links.check(Path("."), "HEAD")
                    git.assert_not_called()

    def test_real_git_context_can_override_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            roots = [Path(directory) / name for name in ("requested", "other")]

            def git(root, *args, env=None):
                return subprocess.check_output(["git", *args], cwd=root, env=env, timeout=10)

            for root in roots:
                root.mkdir()
                git(root, "init", "-q")
                (root / (root.name + ".txt")).write_text("synthetic", encoding="utf-8")
                git(root, "add", ".")
            requested, other = roots
            for name, value in (
                ("GIT_DIR", str(other / ".git")),
                ("GIT_INDEX_FILE", str(other / ".git/index")),
            ):
                with self.subTest(name=name):
                    env = {**os.environ, name: value}
                    self.assertEqual(git(requested, "ls-files", "-z", env=env), b"other.txt\0")
                    with (
                        patch.dict(os.environ, {name: value}),
                        patch.object(verify, "ROOT", requested),
                    ):
                        with self.assertRaisesRegex(ValueError, "^git_repository_override$"):
                            verify.tracked_files()
            with patch.object(verify, "ROOT", requested):
                self.assertEqual(verify.tracked_files(), {"requested.txt"})

    def test_cli_rejects_without_echoing_override(self):
        script = Path(public_links.__file__).resolve()
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(script), "HEAD", "--repo", directory],
                env={**os.environ, "GIT_DIR": "synthetic-private-value"},
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "invalid_public_tree\n")

    def test_linked_worktree_uses_its_own_index_without_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main"
            root.mkdir()

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, timeout=10)

            git("init", "-q")
            (root / "README.md").write_text("Synthetic fixture", encoding="utf-8")
            git("add", ".")
            tree = git("write-tree").decode().strip()
            commit = (
                git(
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "commit-tree",
                    tree,
                    "-m",
                    "synthetic",
                )
                .decode()
                .strip()
            )
            git("update-ref", "HEAD", commit)
            linked = Path(directory) / "linked"
            git("worktree", "add", "--quiet", "--detach", str(linked), commit)
            self.assertTrue((linked / ".git").is_file())
            (linked / "local.txt").write_text("Synthetic fixture", encoding="utf-8")
            subprocess.check_output(["git", "add", "local.txt"], cwd=linked, timeout=10)
            with patch.object(verify, "ROOT", linked):
                self.assertEqual(verify.tracked_files(), {"README.md", "local.txt"})
            with patch.object(verify, "ROOT", root):
                self.assertEqual(verify.tracked_files(), {"README.md"})
            self.assertEqual(public_links.check(linked, "HEAD"), {"tree": tree, "missing": []})

    def test_unrelated_environment_is_preserved(self):
        controls = {"GIT_NO_LAZY_FETCH": "0", "GIT_ALLOW_PROTOCOL": "file", "GIT_TRACE": "0"}
        with patch.dict(os.environ, controls):
            with self.fixture("value = 1") as (_, calls):
                verify.run()
                self.assertEqual(len(calls), 5)
            with patch.object(public_links, "git_output", side_effect=[b"tree\n", b""]) as git:
                self.assertEqual(
                    public_links.check(Path("."), "HEAD"), {"tree": "tree", "missing": []}
                )
            child_env = git.call_args.kwargs["env"]
            self.assertEqual(child_env["GIT_NO_LAZY_FETCH"], "1")
            self.assertEqual(child_env["GIT_ALLOW_PROTOCOL"], "")
            self.assertEqual(child_env["GIT_TRACE"], "0")
            self.assertEqual({name: os.environ[name] for name in controls}, controls)
