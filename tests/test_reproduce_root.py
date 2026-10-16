"""A clean Git status cannot admit a redirected reproduction checkout root."""

import contextlib
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_reproduce_report as report
from test_package_source_links import windows_attributes

from scripts import reproduce


class ReproductionRoot(unittest.TestCase):
    def test_real_git_clean_redirect_is_rejected_and_original_can_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()

            def git(*args):
                return subprocess.check_output(
                    [
                        "git",
                        "-c",
                        "user.name=Reproduction Fixture",
                        "-c",
                        "user.email=fixture@example.invalid",
                        "-c",
                        "commit.gpgsign=false",
                        "-c",
                        "core.hooksPath=" + str(root / "no-hooks"),
                        *args,
                    ],
                    cwd=source,
                    text=True,
                    stderr=subprocess.PIPE,
                    timeout=5,
                ).strip()

            git("init", "--quiet")
            (source / "source.txt").write_bytes(b"original source\n")
            git("add", ".")
            git("commit", "--quiet", "-m", "synthetic source")
            revision = git("rev-parse", "HEAD")
            reproduce.validate_source(source, revision)
            original = root / "original"
            source.rename(original)
            try:
                source.symlink_to(original, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlinks unavailable on this host")
            self.assertEqual(git("status", "--porcelain"), "")
            with patch.object(reproduce, "_git_output") as read:
                with self.assertRaisesRegex(ValueError, "^reproduction_source_changed$"):
                    reproduce.validate_source(source, revision)
                read.assert_not_called()
            self.assertTrue(source.is_symlink())
            self.assertEqual((original / "source.txt").read_bytes(), b"original source\n")
            source.unlink()
            original.rename(source)
            reproduce.validate_source(source, revision)

    def test_missing_file_and_reparse_roots_reject_before_git(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "file"
            file.write_bytes(b"not a checkout")
            for kind in ("missing", "file", "reparse"):
                with self.subTest(kind=kind), contextlib.ExitStack() as stack:
                    source = root if kind == "reparse" else root / kind
                    if kind == "reparse":
                        stack.enter_context(
                            windows_attributes(source, stat.FILE_ATTRIBUTE_REPARSE_POINT)
                        )
                    read = stack.enter_context(patch.object(reproduce, "_git_output"))
                    with self.assertRaisesRegex(ValueError, "^reproduction_source_changed$"):
                        reproduce.validate_source(source, "a" * 40)
                    read.assert_not_called()

    def test_redirected_root_stops_next_child_and_retains_evidence(self):
        # The harness models Python stages. Every completed child, including
        # both isolated consumers, is followed by source admission.
        for stage in range(10):
            with self.subTest(stage=stage), contextlib.ExitStack() as stack:
                calls = []

                def child(args, kwargs, workspace, stage=stage, calls=calls, stack=stack):
                    calls.append(args)
                    if len(calls) > stage + 1:
                        raise AssertionError("next child received redirected checkout")
                    if len(calls) == stage + 1:
                        stack.enter_context(
                            windows_attributes(
                                workspace / "source", stat.FILE_ATTRIBUTE_REPARSE_POINT
                            )
                        )

                def retained(workspace, diagnostics):
                    self.assertTrue(workspace.is_dir())
                    self.assertIn(str(workspace), diagnostics)
                    self.assertEqual(
                        (workspace / "source/examples/person-blackout.json").read_bytes(), b"{}"
                    )

                output, error, _, _, _ = report.ReproductionReport().invoke(
                    python_child=child, inspect_workspace=retained
                )
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "reproduction_source_changed")
                self.assertEqual(len(calls), stage + 1)
                self.assertEqual(output, "")

    def test_ordinary_windows_root_attributes_allow_consumers(self):
        with contextlib.ExitStack() as stack:

            def child(args, kwargs, workspace):
                if args[1:2] == ["scripts/verify.py"]:
                    stack.enter_context(
                        windows_attributes(
                            workspace / "source",
                            stat.FILE_ATTRIBUTE_ARCHIVE | stat.FILE_ATTRIBUTE_READONLY,
                        )
                    )

            output, error, consumers, _, _ = report.ReproductionReport().invoke(
                python_child=child, real_consumers=True, check_workspace=True
            )
        self.assertIsNone(error)
        self.assertIn('"byte_identical_builds": true', output)
        self.assertEqual(len(consumers), 2)


if __name__ == "__main__":
    unittest.main()
