"""Independent negative controls for installed-source evidence."""

import importlib.util
import tempfile
import unittest
from base64 import urlsafe_b64encode
from hashlib import sha256
from importlib.metadata import Distribution
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/passport_install_check.py"
SPEC = importlib.util.spec_from_file_location("passport_install_check", SCRIPT)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class InstalledSourceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source_root = self.root / "source"
        self.source_root.mkdir()
        self.source = self.source_root / "module.py"
        self.source.write_bytes(b"value = 1\n")
        self.installed = self.root / "installed.py"
        self.installed.write_bytes(self.source.read_bytes())

    def test_identical_external_copy_is_accepted(self):
        CHECKER.check_file(self.source, self.installed, self.source_root)

    def test_changed_bytes_are_rejected_even_if_behavior_is_identical(self):
        self.installed.write_bytes(b"# stale build\nvalue = 1\n")
        with self.assertRaisesRegex(ValueError, "installed_source_mismatch"):
            CHECKER.check_file(self.source, self.installed, self.source_root)

    def test_source_tree_import_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "source_tree_import"):
            CHECKER.check_file(self.source, self.source, self.source_root)

    def test_other_file_inside_source_tree_is_rejected(self):
        alternate = self.source_root / "build.py"
        alternate.write_bytes(self.source.read_bytes())
        with self.assertRaisesRegex(ValueError, "source_tree_import"):
            CHECKER.check_file(self.source, alternate, self.source_root)

    def test_missing_installed_file_fails_closed(self):
        self.installed.unlink()
        with self.assertRaises(FileNotFoundError):
            CHECKER.check_file(self.source, self.installed, self.source_root)


class InstalledRecordTests(unittest.TestCase):
    def setUp(self):
        InstalledSourceTests.setUp(self)
        self.info = self.root / "aethron-0.2.0.dist-info"
        self.info.mkdir()
        (self.info / "METADATA").write_text(
            "Metadata-Version: 2.4\nName: aethron\nVersion: 0.2.0\n"
        )
        self.source_bytes = self.source.read_bytes()
        digest = urlsafe_b64encode(sha256(self.source_bytes).digest()).decode().rstrip("=")
        self.row = f"installed.py,sha256={digest},{len(self.source_bytes)}\n"
        self.record = self.info / "RECORD"
        self.record.write_text(self.row)

    def check_record(self, installed=None):
        CHECKER.check_record(
            Distribution.at(self.info),
            "installed.py",
            installed or self.installed,
            self.source_bytes,
        )

    def test_matching_record_is_accepted(self):
        self.check_record()

    def test_missing_record_is_rejected(self):
        self.record.unlink()
        with self.assertRaisesRegex(ValueError, "missing_distribution_record"):
            self.check_record()

    def test_missing_or_duplicate_member_is_rejected(self):
        for record in ("different.py,,\n", self.row * 2):
            with self.subTest(record=record):
                self.record.write_text(record)
                with self.assertRaisesRegex(ValueError, "invalid_distribution_member"):
                    self.check_record()

    def test_identical_copy_outside_record_location_is_rejected(self):
        alternate = self.root / "unowned.py"
        alternate.write_bytes(self.source_bytes)
        # The original byte check accepts this copy; RECORD association must not.
        CHECKER.check_file(self.source, alternate, self.source_root)
        with self.assertRaisesRegex(ValueError, "distribution_location_mismatch"):
            self.check_record(alternate)

    def test_missing_wrong_hash_algorithm_or_digest_is_rejected(self):
        for value in ("", "sha512=wrong", "sha256=wrong"):
            with self.subTest(value=value):
                self.record.write_text(f"installed.py,{value},{len(self.source_bytes)}\n")
                with self.assertRaisesRegex(ValueError, "distribution_hash_mismatch"):
                    self.check_record()

    def test_missing_or_wrong_size_is_rejected(self):
        for value in ("", str(len(self.source_bytes) + 1)):
            with self.subTest(value=value):
                self.record.write_text(self.row.rsplit(",", 1)[0] + f",{value}\n")
                with self.assertRaisesRegex(ValueError, "distribution_size_mismatch"):
                    self.check_record()


class InstalledIdentityTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.info = self.root / "aethron-0.2.0.dist-info"
        self.info.mkdir()
        self.metadata = self.info / "METADATA"
        self.metadata.write_text("Metadata-Version: 2.4\nName: aethron\nVersion: 0.2.0\n")
        self.project = self.root / "pyproject.toml"
        self.project.write_text('[project]\nname = "aethron"\nversion = "0.2.0"\n')

    def check_identity(self):
        CHECKER.check_identity(Distribution.at(self.info), self.project)

    def test_matching_static_identity_is_accepted(self):
        self.check_identity()

    def test_wrong_or_missing_installed_identity_is_rejected(self):
        for fields in (
            "Name: other\nVersion: 0.2.0\n",
            "Name: aethron\nVersion: 0.1.0\n",
            "Name: aethron\n",
            "Version: 0.2.0\n",
        ):
            with self.subTest(fields=fields):
                self.metadata.write_text("Metadata-Version: 2.4\n" + fields)
                with self.assertRaisesRegex(ValueError, "installed_identity_mismatch"):
                    self.check_identity()

    def test_missing_nonstring_or_dynamic_source_version_is_rejected(self):
        for field in (
            "",
            "version = 2\n",
            'version = ""\n',
            'dynamic = ["version"]\n',
            'version = "0.2.0"\ndynamic = ["version"]\n',
        ):
            with self.subTest(field=field):
                self.project.write_text('[project]\nname = "aethron"\n' + field)
                with self.assertRaisesRegex(ValueError, "invalid_source_identity"):
                    self.check_identity()

    def test_duplicate_toml_version_is_rejected(self):
        self.project.write_text(self.project.read_text() + 'version = "0.2.0"\n')
        with self.assertRaises(ValueError):
            self.check_identity()


if __name__ == "__main__":
    unittest.main()
