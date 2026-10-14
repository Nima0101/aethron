"""Release evidence must not select a foreign repository through inherited context."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import edge_reproduce, release, reproduce
from tests.test_git_context import OVERRIDES


class ReleaseGitContext(unittest.TestCase):
    def test_all_entry_points_reject_before_children_or_workspace_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            operations = (
                lambda: release.build(root / "release"),
                lambda: release.committed_blobs("HEAD", root=root),
                lambda: reproduce.validate_source(root, "a" * 40),
                lambda: reproduce.validate_source_manifest(root, "a" * 40, {}),
                reproduce.run,
                lambda: edge_reproduce.run(root / "wheelhouse"),
            )
            for index, operation in enumerate(operations):
                for name in OVERRIDES:
                    for value in ("", "synthetic-private-value"):
                        with (
                            self.subTest(entry=index, name=name, value=value),
                            patch.dict(os.environ, {name: value}),
                            patch.object(edge_reproduce, "ROOT", root),
                            patch.object(subprocess, "run") as run,
                            patch.object(subprocess, "check_output") as read,
                            patch.object(Path, "mkdir") as mkdir,
                            patch.object(tempfile, "mkdtemp") as workspace,
                            contextlib.redirect_stdout(io.StringIO()) as output,
                            contextlib.redirect_stderr(io.StringIO()) as diagnostic,
                        ):
                            with self.assertRaisesRegex(ValueError, "^git_repository_override$"):
                                operation()
                            run.assert_not_called()
                            read.assert_not_called()
                            mkdir.assert_not_called()
                            workspace.assert_not_called()
                            self.assertEqual(output.getvalue(), "")
                            self.assertEqual(diagnostic.getvalue(), "")
                            self.assertEqual(os.environ[name], value)

    def git(self, root, *args):
        return (
            subprocess.check_output(
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
                stderr=subprocess.PIPE,
                timeout=10,
            )
            .decode()
            .strip()
        )

    def repository(self, root, label):
        root.mkdir()
        self.git(root, "init", "--quiet")
        files = {
            "LICENSE": b"synthetic license\n",
            "NOTICE": b"synthetic notice\n",
            "aethron/models/rules.json": json.dumps({"fixture": label}).encode(),
        }
        for name, payload in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        self.git(root, "add", ".")
        self.git(root, "commit", "--quiet", "-m", label)
        return self.git(root, "rev-parse", "HEAD"), files

    def test_real_foreign_repository_cannot_supply_release_bytes_or_clean_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requested, foreign = root / "requested", root / "foreign"
            revision, files = self.repository(requested, "requested")
            foreign_revision, _ = self.repository(foreign, "foreign")
            context = {"GIT_DIR": str(foreign / ".git"), "GIT_WORK_TREE": str(foreign)}
            with patch.dict(os.environ, context), patch.object(release, "ROOT", requested):
                # Demonstrate real Git's cwd override independently of application code.
                self.assertEqual(self.git(requested, "rev-parse", "HEAD"), foreign_revision)
                with self.assertRaisesRegex(ValueError, "^git_repository_override$"):
                    release.build(root / "rejected")
                with self.assertRaisesRegex(ValueError, "^git_repository_override$"):
                    release.committed_blobs("HEAD", root=requested)
                with self.assertRaisesRegex(ValueError, "^git_repository_override$"):
                    reproduce.validate_source(requested, foreign_revision)
                self.assertFalse((root / "rejected").exists())
            reproduce.validate_source(requested, revision)
            self.assertEqual(release.committed_blobs(revision, root=requested), files)

    def test_default_linked_worktree_build_and_unrelated_environment_remain_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, linked = root / "source", root / "linked"
            revision, files = self.repository(source, "linked fixture")
            self.git(source, "worktree", "add", "--quiet", "--detach", str(linked), revision)
            controls = {"GIT_ALLOW_PROTOCOL": "file", "GIT_TRACE": "0", "AETHRON_TEST": "keep"}
            with patch.dict(os.environ, controls), patch.object(release, "ROOT", linked):
                self.assertTrue((linked / ".git").is_file())
                reproduce.validate_source(linked, revision)
                self.assertEqual(release.committed_blobs(revision), files)
                self.assertEqual(release.build(root / "release"), revision)
                manifest = json.loads((root / "release/source-manifest.json").read_bytes())
                reproduce.validate_source_manifest(linked, revision, manifest)
                self.assertEqual({key: os.environ[key] for key in controls}, controls)
                reproduce.validate_source(linked, revision)

    def test_script_and_module_entry_points_do_not_echo_override_values(self):
        for name in ("release", "reproduce", "edge_reproduce"):
            for module in (False, True):
                with self.subTest(script=name, module=module):
                    command = (
                        ["-m", "scripts." + name]
                        if module
                        else [str(Path(release.__file__).with_name(name + ".py"))]
                    )
                    result = subprocess.run(
                        [sys.executable, *command],
                        cwd=release.ROOT,
                        env={**os.environ, "GIT_DIR": "synthetic-private-value"},
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, b"")
                    self.assertIn(b"git_repository_override", result.stderr)
                    self.assertNotIn(b"synthetic-private-value", result.stderr)


if __name__ == "__main__":
    unittest.main()
