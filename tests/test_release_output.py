"""Reject reused artifact destinations without touching their existing contents."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import release


class ReleaseOutputAdmission(unittest.TestCase):
    def attempt(self, root, destination, dirty=b""):
        source = root / "source"
        source.mkdir()
        (source / "fixture.txt").write_bytes(b"synthetic source")

        def git_output(args, **kwargs):
            self.assertEqual(kwargs["cwd"], source)
            if args == ["git", "--no-replace-objects", "ls-files", "-v", "-z"]:
                return b"H fixture.txt\0"
            if args == ["git", "--no-replace-objects", "rev-parse", "HEAD"]:
                return "1" * 40 + "\n"
            if args == [
                "git",
                "--no-replace-objects",
                "status",
                "--porcelain",
                "--untracked-files=normal",
            ]:
                return dirty
            self.fail(f"unexpected Git request: {args}")

        with (
            patch.object(release, "ROOT", source),
            patch.object(
                release,
                "committed_blobs",
                return_value={
                    "fixture.txt": b"synthetic source",
                    "LICENSE": b"synthetic license",
                    "NOTICE": b"synthetic notice",
                    "aethron/models/rules.json": b"{}",
                },
            ),
            patch.object(release.subprocess, "check_output", side_effect=git_output),
            patch.object(release.io, "BytesIO", side_effect=RuntimeError("archive_boundary")),
        ):
            try:
                release.build(destination)
            except (SystemExit, OSError, RuntimeError) as error:
                return error
        self.fail("probe unexpectedly generated release artifacts")

    def test_existing_directories_are_rejected_without_changes(self):
        for contents in ({}, {"old.whl": b"stale", "SHA256SUMS": b"old evidence"}):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                destination = root / "output"
                destination.mkdir()
                for name, data in contents.items():
                    (destination / name).write_bytes(data)
                error = self.attempt(root, destination)
                self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, contents)
                self.assertIsInstance(error, FileExistsError)

    def test_existing_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "output"
            destination.write_bytes(b"existing file")
            error = self.attempt(root, destination)
            self.assertIsInstance(error, FileExistsError)
            self.assertEqual(destination.read_bytes(), b"existing file")

    def test_new_destination_reaches_archive_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "parent" / "output"
            error = self.attempt(root, destination)
            self.assertIsInstance(error, RuntimeError)
            self.assertEqual(str(error), "archive_boundary")
            self.assertFalse(destination.exists())
            self.assertTrue(destination.parent.is_dir())

    def test_dirty_source_still_rejects_before_creating_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "output"
            error = self.attempt(root, destination, dirty=b"?? fixture.txt\n")
            self.assertIsInstance(error, SystemExit)
            self.assertEqual(str(error), "release requires clean committed source")
            self.assertFalse(destination.exists())
