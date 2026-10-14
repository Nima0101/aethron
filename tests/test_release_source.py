"""Synthetic source admission probes; stop before creating an archive."""

import stat
import tempfile
import traceback
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from test_package_source_links import windows_attributes

from scripts import release


class ReleaseSourceAdmission(unittest.TestCase):
    def attempt(self, source, names, destination, blob_error=None):
        reads = []
        read_bytes = Path.read_bytes

        def record_read(path):
            reads.append(path)
            return read_bytes(path)

        def git_output(args, **kwargs):
            self.assertEqual(kwargs["cwd"], source)
            if args == ["git", "--no-replace-objects", "ls-files", "-v", "-f", "-z"]:
                return ("\0".join("H " + name for name in names) + "\0").encode()
            if args == ["git", "--no-replace-objects", "rev-parse", "HEAD"]:
                return "1" * 40 + "\n"
            if args == [
                "git",
                "--no-replace-objects",
                "status",
                "--porcelain",
                "--untracked-files=normal",
            ]:
                return b""
            self.fail(f"unexpected Git request: {args}")

        with (
            patch.object(release, "ROOT", source),
            patch.object(
                release,
                "committed_blobs",
                return_value={
                    "fixture.txt": b"synthetic",
                    "LICENSE": b"synthetic license",
                    "NOTICE": b"synthetic notice",
                    "aethron/models/rules.json": b"{}",
                },
                side_effect=blob_error,
            ),
            patch.object(release.subprocess, "check_output", side_effect=git_output),
            patch.object(Path, "read_bytes", record_read),
            patch.object(release.io, "BytesIO", side_effect=RuntimeError("archive_boundary")),
        ):
            try:
                release.build(destination)
            except (SystemExit, OSError, RuntimeError) as error:
                return error, reads
        self.fail("probe unexpectedly generated release artifacts")

    def assert_rejected(self, source, names, destination):
        error, reads = self.attempt(source, names, destination)
        self.assertIsInstance(error, SystemExit)
        self.assertEqual(str(error), "release requires regular source files without symlinks")
        self.assertEqual(reads, [])
        self.assertFalse(destination.exists())

    def test_symlinks_are_rejected_before_any_source_read(self):
        for kind in ("external", "internal", "dangling", "cycle", "parent"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "source"
                source.mkdir()
                ordinary = source / "a.txt"
                ordinary.write_bytes(b"ordinary synthetic source")
                outside = root / "outside"
                outside.mkdir()
                external = outside / "fixture.txt"
                external.write_bytes(b"synthetic private fixture")
                link = source / "z-link"
                targets = {
                    "external": external,
                    "internal": ordinary,
                    "dangling": root / "missing",
                    "cycle": link,
                    "parent": outside,
                }
                link.symlink_to(targets[kind], target_is_directory=kind == "parent")
                name = "z-link/fixture.txt" if kind == "parent" else "z-link"
                self.assert_rejected(source, ["a.txt", name], root / "output")
                self.assertEqual(external.read_bytes(), b"synthetic private fixture")

    def test_directory_entry_is_rejected_before_any_source_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "a.txt").write_bytes(b"ordinary")
            (source / "z-directory").mkdir()
            self.assert_rejected(source, ["a.txt", "z-directory"], root / "output")

    def test_reparse_sources_reject_before_archive_creation(self):
        # Model Windows metadata on Linux; this is not native junction evidence.
        for location in ("package", "package/nested", "package/nested/source.py"):
            for attributes in (
                stat.FILE_ATTRIBUTE_REPARSE_POINT,
                stat.FILE_ATTRIBUTE_REPARSE_POINT | stat.FILE_ATTRIBUTE_ARCHIVE,
            ):
                with self.subTest(location=location, attributes=attributes):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        source = root / "source"
                        name = "package/nested/source.py"
                        path = source / name
                        path.parent.mkdir(parents=True)
                        path.write_bytes(b"# ordinary source\n")
                        with windows_attributes(source / location, attributes):
                            self.assert_rejected(source, [name], root / "output")

    def test_ordinary_windows_attributes_reach_archive_boundary(self):
        for location in ("package", "package/nested", "package/nested/source.py"):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "source"
                name = "package/nested/source.py"
                path = source / name
                path.parent.mkdir(parents=True)
                path.write_bytes(b"# ordinary source\n")
                with windows_attributes(
                    source / location, stat.FILE_ATTRIBUTE_READONLY | stat.FILE_ATTRIBUTE_ARCHIVE
                ):
                    error, reads = self.attempt(source, [name], root / "output")
                self.assertIsInstance(error, RuntimeError)
                self.assertEqual(str(error), "archive_boundary")
                self.assertEqual(reads, [])
                self.assertFalse((root / "output").exists())

    def test_regular_nested_sources_reach_archive_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "nested").mkdir(parents=True)
            contents = {"a.txt": b"one", "nested/b.txt": b"two"}
            for name, data in contents.items():
                (source / name).write_bytes(data)
            error, reads = self.attempt(source, list(contents), root / "output")
            self.assertIsInstance(error, RuntimeError)
            self.assertEqual(str(error), "archive_boundary")
            self.assertEqual(reads, [])
            self.assertEqual({name: (source / name).read_bytes() for name in contents}, contents)
            self.assertFalse((root / "output").exists())

    def test_source_io_errors_have_fixed_diagnostics(self):
        original_lstat = Path.lstat
        for operation in ("missing", "lstat", "committed_blobs"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "private-owner-fixture"
                source.mkdir()
                name = "private-record.txt"
                path = source / name
                if operation != "missing":
                    path.write_bytes(b"synthetic private bytes")

                def source_stat(candidate, path=path):
                    if candidate == path:
                        raise PermissionError(13, "private detail", str(path))
                    return original_lstat(candidate)

                fault = (
                    nullcontext()
                    if operation in ("missing", "committed_blobs")
                    else patch.object(
                        Path,
                        operation,
                        source_stat,
                    )
                )
                with fault:
                    error, _ = self.attempt(
                        source,
                        [name],
                        root / "output",
                        PermissionError(13, "private detail", str(path))
                        if operation == "committed_blobs"
                        else None,
                    )
                self.assertIsInstance(error, SystemExit)
                self.assertEqual(str(error), "release source unavailable")
                rendered = "".join(
                    traceback.format_exception(type(error), error, error.__traceback__)
                )
                for private in ("private-owner-fixture", name, "private detail"):
                    self.assertNotIn(private, rendered)
                self.assertFalse((root / "output").exists())
