"""The builder must not sign an inventory the installed verifier cannot accept."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "bundle_signer", ROOT / "packaging/appliance/image/sign_bundle.py"
)
signer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(signer)


@unittest.skipIf(os.name == "nt", "requires local symlink permission")
class BundleSigning(unittest.TestCase):
    def test_known_venv_alias_is_removed_without_deleting_library(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = root / "venv/lib"
            library.mkdir(parents=True)
            (library / "code.py").write_text("# fixture\n")
            alias = root / "venv/lib64"
            alias.symlink_to("lib", target_is_directory=True)
            signer.normalize_venv_alias(root)
            self.assertFalse(alias.is_symlink())
            self.assertEqual((library / "code.py").read_text(), "# fixture\n")
            with patch.object(signer.subprocess, "run") as command:
                signer.sign(root, 1)
                command.assert_called_once()
            self.assertEqual(
                set(json.loads((root / "manifest.json").read_text())["files"]),
                {"venv/lib/code.py"},
            )

    def test_unknown_venv_alias_is_never_removed_or_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "venv").mkdir()
            alias = root / "venv/lib64"
            alias.symlink_to("../../outside", target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "unexpected_venv_alias"):
                signer.normalize_venv_alias(root)
            self.assertTrue(alias.is_symlink())

    def test_unsigned_link_rejected_before_manifest_or_signing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "code.py").write_text("# fixture\n")
            (root / "alias").symlink_to("missing", target_is_directory=True)
            with patch.object(signer.subprocess, "run") as command:
                with self.assertRaisesRegex(ValueError, "unsupported_bundle_entry"):
                    signer.sign(root, 1)
                command.assert_not_called()
            self.assertFalse((root / "manifest.json").exists())

    def test_linked_venv_parent_cannot_delete_an_external_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle, outside = root / "bundle", root / "outside"
            bundle.mkdir()
            (outside / "lib").mkdir(parents=True)
            (outside / "lib64").symlink_to("lib", target_is_directory=True)
            (bundle / "venv").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "unexpected_venv_alias"):
                signer.normalize_venv_alias(bundle)
            self.assertTrue((outside / "lib64").is_symlink())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO")
    def test_special_file_rejected_before_signing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os.mkfifo(root / "pipe")
            with patch.object(signer.subprocess, "run") as command:
                with self.assertRaisesRegex(ValueError, "unsupported_bundle_entry"):
                    signer.sign(root, 1)
                command.assert_not_called()
