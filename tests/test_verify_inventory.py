"""Synthetic tracked-file coverage; no product child command runs."""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify
from tests import test_verify_static as static_checks


class TrackedInventory(unittest.TestCase):
    fixture = static_checks.StaticCheckClaims.fixture

    def test_missing_tracked_text_prevents_success(self):
        for name in (
            "README.md",
            "docs/missing.txt",
            "integrations/missing.json",
            "tests/build/missing.py",
        ):
            with self.subTest(name=name), self.fixture("value = 1") as (output, calls):
                with (
                    patch.object(verify, "git_output", return_value=(name + "\0").encode()),
                    self.assertRaisesRegex(AssertionError, "missing tracked content"),
                ):
                    verify.run()
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(len(calls), 1)

    def test_directory_cannot_substitute_for_tracked_text(self):
        with self.fixture("value = 1") as (output, calls):
            name = "docs/guide.md"
            (verify.ROOT / name).mkdir()
            with (
                patch.object(verify, "git_output", return_value=(name + "\0").encode()),
                self.assertRaisesRegex(AssertionError, "missing tracked content"),
            ):
                verify.run()
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(len(calls), 1)

    def test_malformed_inventory_prevents_success(self):
        for data in (
            b"docs/example.md",
            b"\0",
            b"docs/example.md\0\0",
            b"../outside.txt\0",
            b"/outside.txt\0",
            b"./README.md\0",
            b"docs//example.md\0",
            b".\0",
            b"docs/\xff.txt\0",
        ):
            with self.subTest(data=data), self.fixture("value = 1") as (output, calls):
                with (
                    patch.object(verify, "git_output", return_value=data),
                    self.assertRaisesRegex(ValueError, "invalid tracked inventory"),
                ):
                    verify.run()
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(len(calls), 1)

    def test_names_are_nul_delimited_not_line_or_quote_delimited(self):
        names = {'docs/quote"name.txt', "docs/line\nbreak.txt", "docs/space name.txt"}
        data = "".join(name + "\0" for name in sorted(names)) * 2
        with (
            patch.object(verify, "require_worktree_root"),
            patch.object(verify, "git_output", return_value=data.encode()) as command,
        ):
            self.assertEqual(verify.tracked_files(), names)
        command.assert_called_once_with(
            ["git", "ls-files", "--cached", "--full-name", "-z"],
            cwd=verify.ROOT,
            timeout=30,
        )

    def test_tracked_names_with_spaces_and_unicode_are_scanned(self):
        for leaf in ("space name.txt", "räksmörgås.txt"):
            with self.subTest(leaf=leaf), self.fixture("value = 1") as (_, calls):
                name = "docs/" + leaf
                (verify.ROOT / name).write_text("synthetic", encoding="utf-8")
                # Git can repeat names when several index stages exist.
                with patch.object(verify, "git_output", return_value=((name + "\0") * 2).encode()):
                    verify.run()
                self.assertEqual(len(calls), 5)

    def test_coverage_does_not_expand_scan_roots_or_extensions(self):
        with self.fixture("value = 1") as (_, calls):
            data = b"private/missing.txt\0docs/missing.bin\0archive.zip\0"
            with patch.object(verify, "git_output", return_value=data):
                verify.run()
            self.assertEqual(len(calls), 5)

    def test_real_git_inventory_keeps_unstaged_deletions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, timeout=10)

            git("init", "-q")
            names = {"space name.txt", "räksmörgås.txt"}
            for name in names:
                (root / name).write_text("synthetic", encoding="utf-8")
            git("add", "--", *sorted(names))
            (root / "space name.txt").unlink()
            with patch.object(verify, "ROOT", root):
                self.assertEqual(verify.tracked_files(), names)
                git("add", "-u")
                self.assertEqual(verify.tracked_files(), {"räksmörgås.txt"})

    def test_inventory_command_failure_prevents_success(self):
        with self.fixture("value = 1") as (output, calls):
            failure = subprocess.CalledProcessError(7, ["git", "ls-files"])
            with (
                patch.object(verify, "git_output", side_effect=failure),
                self.assertRaises(subprocess.CalledProcessError) as caught,
            ):
                verify.run()
            self.assertIs(caught.exception, failure)
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(len(calls), 1)

    def test_empty_inventory_still_scans_untracked_text(self):
        with self.fixture("value = 1") as (output, calls):
            (verify.ROOT / "docs/example.txt").write_text(
                "BEGIN " + "PRIVATE KEY", encoding="utf-8"
            )
            with self.assertRaisesRegex(AssertionError, "public leak"):
                verify.run()
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(len(calls), 1)
