"""A hash-correct source archive must have an extractable file namespace."""

import gzip
import hashlib
import io
import json
import tarfile
import unittest
from unittest.mock import patch

from scripts import reproduce


class ReleasePathConflicts(unittest.TestCase):
    def archive(self, names):
        payload = b"synthetic source\n"
        manifest = {name: hashlib.sha256(payload).hexdigest() for name in names}
        buffer = io.BytesIO()
        with tarfile.open(
            fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT, encoding="utf-8"
        ) as archive:
            for name in names:
                member = tarfile.TarInfo("aethron-0.2.0/" + name)
                member.size = len(payload)
                member.mode = 0o644
                archive.addfile(member, io.BytesIO(payload))
        compressed = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed, mode="wb", mtime=0, compresslevel=9) as stream:
            stream.write(buffer.getvalue())
        return compressed.getvalue(), json.dumps(manifest).encode()

    def test_file_directory_conflicts_reject_in_either_order(self):
        for names in (
            ("source", "source/module.py"),
            ("source/module", "source/module/data.txt"),
            ("source", "source/nested/deep/data.txt"),
            ("café", "café/module.py"),
        ):
            for ordered in (names, names[::-1]):
                with self.subTest(names=ordered):
                    with self.assertRaisesRegex(ValueError, "^release_source_archive_invalid$"):
                        reproduce.validate_source_archive(*self.archive(ordered))

    def test_manifest_conflict_rejects_before_decompression(self):
        archive, manifest = self.archive(("source/module.py", "source"))
        with patch.object(
            reproduce, "_validate_gzip_metadata", side_effect=AssertionError("archive inspected")
        ) as inspect:
            with self.assertRaisesRegex(ValueError, "^release_source_archive_invalid$"):
                reproduce.validate_source_archive(archive, manifest)
        inspect.assert_not_called()

    def test_shared_directories_and_lexical_prefixes_remain_valid(self):
        names = (
            "source/module.py",
            "source/module/data.txt",
            "source/nested/first.txt",
            "source/nested/second.txt",
            "source.txt",
            "sources",
        )
        for ordered in (names, names[::-1]):
            with self.subTest(names=ordered):
                archive, manifest = self.archive(ordered)
                self.assertEqual(
                    reproduce.validate_source_archive(archive, manifest), json.loads(manifest)
                )


if __name__ == "__main__":
    unittest.main()
