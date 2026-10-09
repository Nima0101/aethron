"""Signed runtime hashing retains all bytes with bounded transient memory."""

import hashlib
import os
import tempfile
import tracemalloc
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from aethron_edge.runtime.updates import digest


class BundleDigest(unittest.TestCase):
    def test_multiblock_hash_uses_less_than_half_megabyte_transient_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.bin"
            content = bytes(range(256)) * (16 * 1024) + b"tail"
            path.write_bytes(content)
            expected = hashlib.sha256(content).hexdigest()
            tracemalloc.start()
            try:
                actual = digest(path)
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            self.assertEqual(actual, expected)
            self.assertLess(peak, 512 * 1024)
            with path.open("r+b") as stream:
                stream.seek(-1, os.SEEK_END)
                stream.write(b"!")
            self.assertNotEqual(digest(path), expected)

    def test_small_metadata_file_uses_less_than_64k_transient_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            content = b"x" * 8192
            path.write_bytes(content)
            expected = hashlib.sha256(content).hexdigest()
            tracemalloc.start()
            try:
                actual = digest(path)
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            self.assertEqual(actual, expected)
            self.assertLess(peak, 64 * 1024)

    def test_size_change_between_inspection_and_read_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload"
            original_open = os.fdopen
            for replacement in (b"", b"grew beyond original content"):
                path.write_bytes(b"original")

                def change_before_read(fd, *args, replacement=replacement, **kwargs):
                    with path.open("wb") as target:
                        target.write(replacement)
                    return original_open(fd, *args, **kwargs)

                with (
                    self.subTest(replacement=replacement),
                    patch("os.fdopen", change_before_read),
                ):
                    with self.assertRaisesRegex(ValueError, "invalid_bundle"):
                        digest(path)

    def test_short_reads_preserve_every_byte(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload"
            content = bytes(range(256)) * 3
            path.write_bytes(content)
            original_open = os.fdopen

            @contextmanager
            def short_reads(fd, *args, **kwargs):
                with original_open(fd, *args, **kwargs) as stream:
                    yield SimpleNamespace(
                        readinto=lambda target: stream.readinto(target[:3]),
                        read=stream.read,
                    )

            with patch("os.fdopen", short_reads):
                self.assertEqual(digest(path), hashlib.sha256(content).hexdigest())

    def test_empty_and_small_payloads_hash_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload"
            for content in (b"", b"a", b"a" * 262144, b"b" * 262145):
                path.write_bytes(content)
                self.assertEqual(digest(path), hashlib.sha256(content).hexdigest())

    def test_nonregular_and_oversize_inputs_rejected_before_open(self):
        import stat
        from types import SimpleNamespace

        for mode, size in (
            (stat.S_IFLNK, 10),
            (stat.S_IFDIR, 0),
            (stat.S_IFREG, 512 * 1024 * 1024 + 1),
        ):
            with (
                patch.object(
                    Path, "lstat", return_value=SimpleNamespace(st_mode=mode, st_size=size)
                ),
                patch("os.open") as opened,
            ):
                with self.assertRaisesRegex(ValueError, "invalid_bundle"):
                    digest(Path("unused"))
                opened.assert_not_called()


if __name__ == "__main__":
    unittest.main()
