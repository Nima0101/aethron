"""Standalone release builds must admit the checkout root before invoking Git."""

import contextlib
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_package_source_links import windows_attributes

from scripts import release


class ReleaseRoot(unittest.TestCase):
    def test_real_git_redirect_rejects_before_output_and_restored_root_can_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()

            def git(*args):
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
                    cwd=source,
                    stderr=subprocess.PIPE,
                    timeout=5,
                )

            blobs = {
                "LICENSE": b"synthetic license\n",
                "NOTICE": b"synthetic notice\n",
                "aethron/models/rules.json": b"{}\n",
            }
            for name, data in blobs.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            git("init", "--quiet")
            git("add", ".")
            git("commit", "--quiet", "-m", "synthetic source")
            original = root / "original"
            source.rename(original)
            try:
                source.symlink_to(original, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlinks unavailable on this host")
            self.assertEqual(git("status", "--porcelain"), b"")
            destination = root / "new-parent" / "output"
            with patch.object(release, "ROOT", source):
                with self.assertRaisesRegex(SystemExit, "^release requires regular source root$"):
                    release.build(destination)
            self.assertFalse(destination.parent.exists())
            self.assertTrue(source.is_symlink())
            self.assertEqual({name: (original / name).read_bytes() for name in blobs}, blobs)

            source.unlink()
            original.rename(source)
            with patch.object(release, "ROOT", source):
                release.build(destination)
                # Ordinary Windows flags must not be mistaken for redirection.
                with windows_attributes(
                    source, stat.FILE_ATTRIBUTE_ARCHIVE | stat.FILE_ATTRIBUTE_READONLY
                ):
                    release.build(root / "repeat")
            self.assertEqual(
                {p.name: p.read_bytes() for p in destination.iterdir()},
                {p.name: p.read_bytes() for p in (root / "repeat").iterdir()},
            )
            self.assertEqual(git("status", "--porcelain"), b"")

    def test_unavailable_and_redirected_roots_reject_before_git(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file").write_bytes(b"not a checkout")
            for kind in ("missing", "file", "reparse", "unreadable"):
                with self.subTest(kind=kind), contextlib.ExitStack() as stack:
                    source = root / kind if kind in ("missing", "file") else root
                    if kind == "reparse":
                        stack.enter_context(
                            windows_attributes(source, stat.FILE_ATTRIBUTE_REPARSE_POINT)
                        )
                    if kind == "unreadable":
                        stack.enter_context(
                            patch.object(Path, "lstat", side_effect=PermissionError("private path"))
                        )
                    stack.enter_context(patch.object(release, "ROOT", source))
                    read = stack.enter_context(
                        patch.object(
                            release,
                            "git_output",
                            side_effect=AssertionError("unadmitted Git child"),
                        )
                    )
                    destination = root / "new-parent" / "output"
                    with self.assertRaisesRegex(
                        SystemExit, "^release requires regular source root$"
                    ) as caught:
                        release.build(destination)
                    if kind in ("missing", "unreadable"):
                        self.assertTrue(caught.exception.__suppress_context__)
                    read.assert_not_called()
                self.assertFalse(destination.parent.exists())


if __name__ == "__main__":
    unittest.main()
