"""Release TAR names must not depend on the host filesystem encoding."""

import gzip
import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import test_release_archive

from scripts import reproduce


@contextmanager
def host_tar_encoding(encoding):
    # Model both defaults captured when tarfile is imported on another host.
    # Leave filesystem access unchanged so this isolates the archive boundary.
    defaults = list(tarfile.TarInfo.tobuf.__defaults__)
    defaults[1] = encoding
    with (
        patch.object(tarfile.TarFile, "encoding", encoding),
        patch.object(tarfile.TarInfo.tobuf, "__defaults__", tuple(defaults)),
    ):
        yield


def source_archive(encoding):
    data = b"synthetic source\n"
    name = "caf\u00e9.txt"
    manifest = {name: hashlib.sha256(data).hexdigest()}
    buffer = io.BytesIO()
    with tarfile.open(
        fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT, encoding=encoding, errors="strict"
    ) as archive:
        member = tarfile.TarInfo("aethron-0.2.0/" + name)
        member.size = len(data)
        member.mode = 0o644
        archive.addfile(member, io.BytesIO(data))
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", mtime=0, compresslevel=9) as stream:
        stream.write(buffer.getvalue())
    return compressed.getvalue(), json.dumps(manifest).encode("utf-8"), manifest


class ReleaseEncoding(unittest.TestCase):
    def test_build_bytes_do_not_depend_on_tar_encoding(self):
        fixture = test_release_archive.ReleaseArchive()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, blobs = fixture.fixture(root)
            name = "caf\u00e9.txt"
            blobs[name] = b"synthetic unicode filename\n"
            (source / name).write_bytes(blobs[name])
            baseline = root / "utf8"
            with host_tar_encoding("utf-8"):
                fixture.build_fixture(source, blobs, baseline)
            expected = {p.name: p.read_bytes() for p in baseline.iterdir()}
            for encoding in ("ascii", "latin-1"):
                with self.subTest(encoding=encoding), host_tar_encoding(encoding):
                    destination = root / encoding
                    fixture.build_fixture(source, blobs, destination)
                    self.assertEqual(
                        {p.name: p.read_bytes() for p in destination.iterdir()}, expected
                    )

    def test_utf8_archive_validates_under_other_host_encodings(self):
        payload, manifest_payload, manifest = source_archive("utf-8")
        for encoding in ("utf-8", "ascii", "latin-1"):
            with self.subTest(encoding=encoding), host_tar_encoding(encoding):
                self.assertEqual(
                    reproduce.validate_source_archive(payload, manifest_payload), manifest
                )

    def test_non_utf8_archive_is_rejected_even_on_matching_host(self):
        payload, manifest_payload, _ = source_archive("latin-1")
        for encoding in ("utf-8", "ascii", "latin-1"):
            with self.subTest(encoding=encoding), host_tar_encoding(encoding):
                with self.assertRaisesRegex(ValueError, "^release_source_archive_invalid$"):
                    reproduce.validate_source_archive(payload, manifest_payload)


if __name__ == "__main__":
    unittest.main()
