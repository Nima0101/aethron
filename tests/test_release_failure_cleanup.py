"""Failed release writes must allow retry without retaining partial artifacts."""

import errno
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_release_archive

from scripts import release


class ReleaseFailureCleanup(unittest.TestCase):
    def test_partial_artifact_writes_leave_destination_available_for_retry(self):
        names = (
            "aethron-0.2.0-source.tar.gz",
            "source-manifest.json",
            "sbom.cdx.json",
            "provenance.json",
            "SHA256SUMS",
        )
        fixture = test_release_archive.ReleaseArchive()
        write_bytes = Path.write_bytes
        for name in names:
            with self.subTest(artifact=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, blobs = fixture.fixture(root)
                destination = root / "new-parent" / "output"
                failure = OSError(errno.ENOSPC, "synthetic full disk")

                def partial_write(path, data, destination=destination, name=name, failure=failure):
                    if path == destination / name:
                        write_bytes(path, data[:7])
                        raise failure
                    return write_bytes(path, data)

                with patch.object(Path, "write_bytes", partial_write):
                    with self.assertRaises(OSError) as caught:
                        fixture.build_fixture(source, blobs, destination)
                self.assertIs(caught.exception, failure)
                self.assertFalse(destination.exists())
                self.assertEqual({n: (source / n).read_bytes() for n in blobs}, blobs)
                fixture.build_fixture(source, blobs, destination)
                fixture.build_fixture(source, blobs, root / "repeat")
                self.assertEqual(
                    {p.name: p.read_bytes() for p in destination.iterdir()},
                    {p.name: p.read_bytes() for p in (root / "repeat").iterdir()},
                )

    def test_zip_failure_and_interruption_close_archive_before_cleanup(self):
        fixture = test_release_archive.ReleaseArchive()
        writestr = release.zipfile.ZipFile.writestr
        for failure in (OSError("synthetic ZIP failure"), KeyboardInterrupt()):
            with self.subTest(failure=type(failure)), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source, blobs = fixture.fixture(root)
                destination = root / "output"
                archives = []

                def interrupted_write(archive, *args, archives=archives, failure=failure, **kwargs):
                    archives.append(archive)
                    writestr(archive, *args, **kwargs)
                    raise failure

                with patch.object(release.zipfile.ZipFile, "writestr", interrupted_write):
                    with self.assertRaises(type(failure)) as caught:
                        fixture.build_fixture(source, blobs, destination)
                self.assertIs(caught.exception, failure)
                self.assertEqual(len(archives), 1)
                self.assertIsNone(archives[0].fp)
                self.assertFalse(destination.exists())
                fixture.build_fixture(source, blobs, destination)
                self.assertEqual(len(list(destination.iterdir())), 6)

    def test_cleanup_failure_retains_original_error_and_partial_output(self):
        fixture = test_release_archive.ReleaseArchive()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, blobs = fixture.fixture(root)
            destination = root / "output"
            write_bytes = Path.write_bytes
            failure = OSError(errno.ENOSPC, "synthetic full disk")
            cleanup_failure = PermissionError("synthetic cleanup denial")

            def partial_write(path, data):
                write_bytes(path, data[:7])
                raise failure

            with (
                patch.object(Path, "write_bytes", partial_write),
                patch.object(Path, "unlink", side_effect=cleanup_failure),
            ):
                with self.assertRaises(PermissionError) as caught:
                    fixture.build_fixture(source, blobs, destination)
            self.assertIs(caught.exception, cleanup_failure)
            self.assertIs(caught.exception.__context__, failure)
            self.assertEqual(len(list(destination.iterdir())), 1)
            self.assertEqual((destination / "aethron-0.2.0-source.tar.gz").stat().st_size, 7)
            with self.assertRaises(FileExistsError):
                fixture.build_fixture(source, blobs, destination)

    def test_cleanup_does_not_remove_unexpected_content_or_parent(self):
        fixture = test_release_archive.ReleaseArchive()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, blobs = fixture.fixture(root)
            destination = root / "output"
            write_bytes = Path.write_bytes
            failure = RuntimeError("synthetic interrupted write")

            def interrupted_write(path, data):
                write_bytes(path, data[:7])
                (destination / "unrelated").mkdir()
                write_bytes(destination / "unrelated" / "keep", b"preserved")
                raise failure

            with patch.object(Path, "write_bytes", interrupted_write):
                with self.assertRaises(OSError) as caught:
                    fixture.build_fixture(source, blobs, destination)
            self.assertIs(caught.exception.__context__, failure)
            self.assertEqual((destination / "unrelated" / "keep").read_bytes(), b"preserved")
            self.assertEqual([p.name for p in destination.iterdir()], ["unrelated"])
            self.assertTrue(root.is_dir())


if __name__ == "__main__":
    unittest.main()
