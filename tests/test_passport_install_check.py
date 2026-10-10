"""Independent negative controls for installed-source evidence."""

import importlib.util
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
