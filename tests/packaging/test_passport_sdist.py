"""Small archive counterexamples; not a local distribution build."""

import importlib.util
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/passport_sdist_check.py"


class SourceArchiveTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("passport_sdist_check", SCRIPT)
        self.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.checker)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.archive = self.root / "example.tar.gz"

    def write_archive(self, entries):
        with tarfile.open(self.archive, "w:gz") as archive:
            for name, content, kind in entries:
                member = tarfile.TarInfo(name)
                member.type = kind
                member.size = len(content) if kind == tarfile.REGTYPE else 0
                member.linkname = "elsewhere" if kind == tarfile.SYMTYPE else ""
                archive.addfile(member, io.BytesIO(content))

    def check(self):
        return self.checker.check_archive(self.archive, "example-1", {"data/input.json": b"{}"})

    def test_matching_member_is_accepted_without_extraction(self):
        self.write_archive([("example-1/data/input.json", b"{}", tarfile.REGTYPE)])
        self.assertEqual(set(self.check()), {"data/input.json"})
        self.assertEqual(list(self.root.iterdir()), [self.archive])

    def test_missing_or_wrong_root_is_rejected(self):
        for entries in ([], [("other-1/data/input.json", b"{}", tarfile.REGTYPE)]):
            with self.subTest(entries=entries):
                self.write_archive(entries)
                with self.assertRaisesRegex(ValueError, "missing_archive_input"):
                    self.check()

    def test_changed_member_is_rejected(self):
        self.write_archive([("example-1/data/input.json", b"[]", tarfile.REGTYPE)])
        with self.assertRaisesRegex(ValueError, "archive_input_mismatch"):
            self.check()

    def test_duplicate_member_is_rejected(self):
        entry = ("example-1/data/input.json", b"{}", tarfile.REGTYPE)
        self.write_archive([entry, entry])
        with self.assertRaisesRegex(ValueError, "duplicate_archive_input"):
            self.check()

    def test_link_and_directory_cannot_stand_in_for_file(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE):
            with self.subTest(kind=kind):
                self.write_archive([("example-1/data/input.json", b"", kind)])
                with self.assertRaisesRegex(ValueError, "invalid_archive_input_type"):
                    self.check()

    def test_larger_member_is_rejected(self):
        self.write_archive([("example-1/data/input.json", b"{}extra", tarfile.REGTYPE)])
        with self.assertRaisesRegex(ValueError, "archive_input_mismatch"):
            self.check()


if __name__ == "__main__":
    unittest.main()
