"""Zip resource loading must remain portable and fail closed on missing artifacts."""

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from aethron.features import load_model

ROOT = Path(__file__).resolve().parents[1]


class ModelResource(unittest.TestCase):
    def test_windows_style_nested_resource_prefix_does_not_break_zipapp(self):
        # Reproduce the real Windows/Python3.9 CI failure with a genuine ZIP
        # reader and its observed nested-package prefix. This is not native Windows execution.
        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "candidate.pyz"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.write(ROOT / "aethron/models/rules.json", "aethron/models/rules.json")
            with zipfile.ZipFile(archive_path) as archive:

                def files(package):
                    prefix = "aethron\\models/" if package == "aethron.models" else "aethron/"
                    return zipfile.Path(archive, at=prefix)

                with patch("aethron.features.resources.files", side_effect=files):
                    self.assertIsInstance(load_model(), dict)

    def test_missing_zip_resource_withdraws_model_instead_of_crashing(self):
        with patch("aethron.features.resources.files", side_effect=KeyError("missing resource")):
            self.assertFalse(load_model())
