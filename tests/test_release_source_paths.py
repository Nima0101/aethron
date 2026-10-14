"""Reject source names that the release archive verifier cannot admit."""

import gzip
import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import release, reproduce

WINDOWS_COLON_NAMES = (
    b"C:",
    b"C:outside",
    b"C:/outside",
    b"source/D:/outside",
    b"file:stream",
    b"file::$DATA",
)

WINDOWS_DEVICE_NAMES = ("CON", "PRN", "AUX", "NUL") + tuple(
    prefix + digit for prefix in ("COM", "LPT") for digit in "123456789¹²³"
)
WINDOWS_DEVICE_PATHS = tuple(
    name.encode("utf-8")
    for device in WINDOWS_DEVICE_NAMES
    for name in (device, device.lower() + ".txt", device + "/file.txt")
)

INVALID_NAMES = (
    (
        b".",
        b"..",
        b"/outside",
        b"a/../outside",
        b"a/./file",
        b"a//file",
        b"a/",
        b"a\\file",
        b"..\\outside",
        b"bad-\xff",
    )
    + WINDOWS_COLON_NAMES
    + WINDOWS_DEVICE_PATHS
)


class ReleaseSourcePaths(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.git("init", "-q")
        self.blob = self.git("hash-object", "-w", "--stdin", data=b"synthetic payload\n")

    def git(self, *args, data=None):
        return subprocess.check_output(
            ["git", *args], cwd=self.root, input=data, stderr=subprocess.PIPE, timeout=10
        ).strip()

    def tree(self, name, *, child=None):
        mode, oid = (b"100644", self.blob) if child is None else (b"40000", child)
        data = mode + b" " + name + b"\0" + bytes.fromhex(oid.decode())
        return self.git("hash-object", "-t", "tree", "-w", "--literally", "--stdin", data=data)

    def assert_rejected(self, tree):
        execute = subprocess.check_output
        calls = []

        def git(args, **kwargs):
            calls.append(args)
            return execute(args, **kwargs)

        with patch.object(release.subprocess, "check_output", side_effect=git):
            with self.assertRaisesRegex(ValueError, "^release_source_path_invalid$"):
                release.committed_blobs(tree.decode(), root=self.root)
        self.assertFalse(any("cat-file" in args for args in calls))

    def test_invalid_blob_names_reject_before_payload_reads(self):
        for name in INVALID_NAMES:
            for nested in (False, True):
                with self.subTest(name=name, nested=nested):
                    tree = self.tree(name)
                    if nested:
                        tree = self.tree(b"source", child=tree)
                    self.assert_rejected(tree)

    def test_invalid_directories_reject_even_without_blobs(self):
        empty = self.git("mktree", data=b"")
        for name in INVALID_NAMES:
            with self.subTest(name=name):
                self.assert_rejected(self.tree(name, child=empty))

    def test_checkout_names_reject_before_filesystem_access(self):
        # Reject before platform Path normalization erases dot components.
        for name in INVALID_NAMES:
            with self.subTest(name=name):
                destination = self.root / "release"

                def git(args, name=name, **kwargs):
                    if "ls-files" in args:
                        return name + b"\0"
                    if "rev-parse" in args:
                        return "a" * 40 + "\n"
                    if "status" in args:
                        return b""
                    self.fail(f"unexpected Git command: {args}")

                with (
                    patch.object(release, "ROOT", self.root),
                    patch.object(release.subprocess, "check_output", side_effect=git),
                    patch.object(Path, "lstat", side_effect=AssertionError("source inspected")),
                    patch.object(
                        release, "committed_blobs", side_effect=AssertionError("payload read")
                    ) as blobs,
                ):
                    with self.assertRaisesRegex(ValueError, "^release_source_path_invalid$"):
                        release.build(destination)
                blobs.assert_not_called()
                self.assertFalse(destination.exists())

    def test_valid_names_preserve_exact_bytes(self):
        for name in (
            b".hidden",
            b"two words",
            b"tab\tline\n",
            "café.txt".encode(),
            b"console",
            b"auxiliary",
            b"null",
            b"COM0",
            b"COM10",
            b"LPT0",
            b"LPT10",
            "COM⁴".encode(),
            b"_NUL",
            b"x.CON",
        ):
            with self.subTest(name=name):
                tree = self.tree(b"source", child=self.tree(name))
                self.assertEqual(
                    release.committed_blobs(tree.decode(), root=self.root),
                    {"source/" + name.decode(): b"synthetic payload\n"},
                )

    def test_archive_rejects_windows_drive_stream_and_device_names(self):
        # Real, otherwise canonical archives must not qualify names rejected
        # before checkout inspection. No Windows filesystem access is needed.
        data = b"synthetic payload\n"
        for raw in WINDOWS_COLON_NAMES + WINDOWS_DEVICE_PATHS:
            with self.subTest(name=raw):
                name = raw.decode()
                manifest = json.dumps({name: hashlib.sha256(data).hexdigest()}).encode()
                buffer = io.BytesIO()
                with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                    member = tarfile.TarInfo("aethron-0.2.0/" + name)
                    member.mode = 0o644
                    member.size = len(data)
                    archive.addfile(member, io.BytesIO(data))
                compressed = io.BytesIO()
                with gzip.GzipFile(
                    fileobj=compressed, mode="wb", mtime=0, compresslevel=9
                ) as stream:
                    stream.write(buffer.getvalue())
                with self.assertRaisesRegex(ValueError, "^release_source_archive_invalid$"):
                    reproduce.validate_source_archive(compressed.getvalue(), manifest)


if __name__ == "__main__":
    unittest.main()
