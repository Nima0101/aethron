"""Exercise public-content exclusions against synthetic files only."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

from scripts import verify


class ScanComplete(Exception):
    pass


class WindowsRelativePath(type(Path())):
    """Model Git's POSIX names versus Windows relative-path spelling."""

    def relative_to(self, *args, **kwargs):
        return PureWindowsPath(super().relative_to(*args, **kwargs))


class PublicContentExclusions(unittest.TestCase):
    markers = (
        "/" + "Users" + "/synthetic",
        "/" + "home" + "/synthetic",
        "BEGIN " + "PRIVATE KEY",
        "ghp_" + "x" * 30,
        "AKIA" + "X" * 16,
    )

    def scan(self, name, text, tracked=True, windows_relative=False):
        with tempfile.TemporaryDirectory() as directory:
            root = (WindowsRelativePath if windows_relative else Path)(directory)
            manifests = root / "docs/verification"
            manifests.mkdir(parents=True)
            for manifest in (
                "governance-freeze.json",
                "architecture-freeze.json",
                "amendment-v2-freeze.json",
                "data-freeze.json",
                "amendment-v3-freeze.json",
                "data-v3-freeze.json",
                "registration-freeze.json",
                "rgb-model-freeze.json",
                "rgb-smoke-freeze.json",
            ):
                (manifests / manifest).write_text(json.dumps({"files": {}}), encoding="utf-8")
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            output = io.StringIO()

            def stop_before_consumers(args, **kwargs):
                if args[1:3] != ["scripts/public_links.py", "HEAD"]:
                    raise ScanComplete

            with (
                patch.object(verify, "ROOT", root),
                # Root identity has real-Git coverage in test_verify_root.
                patch.object(verify, "require_worktree_root"),
                patch.object(verify.subprocess, "run", side_effect=stop_before_consumers),
                patch.object(
                    verify,
                    "git_output",
                    return_value=(name + "\0").encode() if tracked else b"",
                ),
                contextlib.redirect_stdout(output),
            ):
                try:
                    verify.run()
                except (AssertionError, ScanComplete) as error:
                    self.assertEqual(output.getvalue(), "")
                    return error
            self.fail("unexpected completion beyond synthetic scanner boundary")

    def test_same_basename_elsewhere_is_not_exempt(self):
        for name in ("verify.py", "docs/verify.py", "tests/verify.py", "scripts/nested/verify.py"):
            for marker in self.markers:
                with self.subTest(name=name, marker=marker):
                    error = self.scan(name, marker)
                    self.assertIsInstance(error, AssertionError)
                    self.assertEqual(str(error), "public leak: " + str(Path(name)))

    def test_scanner_pattern_file_remains_exempt(self):
        for marker in self.markers:
            with self.subTest(marker=marker):
                self.assertIsInstance(self.scan("scripts/verify.py", marker), ScanComplete)

    def test_ordinary_file_is_checked(self):
        for marker in self.markers:
            with self.subTest(marker=marker):
                self.assertIsInstance(self.scan("docs/example.txt", marker), AssertionError)

    def test_clean_same_basename_is_accepted(self):
        self.assertIsInstance(self.scan("docs/verify.py", "# synthetic clean file"), ScanComplete)

    def test_generated_directory_exclusion_does_not_hide_tracked_files(self):
        name = "tests/build/verify.py"
        marker = self.markers[2]
        self.assertIsInstance(self.scan(name, marker, tracked=False), ScanComplete)
        self.assertIsInstance(self.scan(name, marker, tracked=True), AssertionError)

    def test_git_inventory_uses_posix_names_with_windows_relative_paths(self):
        self.assertIsInstance(
            self.scan("tests/build/example.txt", self.markers[2], windows_relative=True),
            AssertionError,
        )
