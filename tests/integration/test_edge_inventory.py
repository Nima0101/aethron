"""Inventory must describe the selected wheels, never an older build with the same version."""

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import edge_inventory


class EdgeInventory(unittest.TestCase):
    def wheel(self, folder, name, version, marker):
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name.replace("-", "_") + "-" + version + "-" + marker + ".whl")
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                name + ".dist-info/METADATA",
                f"Name: {name}\nVersion: {version}\nLicense-Expression: GPL-3.0-only\n",
            )
            archive.writestr("content.txt", marker)
        return path

    def test_selected_candidate_cannot_be_replaced_by_old_dependency_wheel(self):
        self.assertTrue(hasattr(edge_inventory, "wheel_components"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate"
            dependencies = root / "deps"
            selected = self.wheel(candidate, "aethron-edge", "0.1.0", "new")
            self.wheel(dependencies, "aethron-edge", "0.1.0", "old")
            result = edge_inventory.wheel_components(
                candidate, dependencies, {"aethron-edge": "0.1.0"}
            )
            self.assertEqual(
                result[0]["hashes"][0]["content"], hashlib.sha256(selected.read_bytes()).hexdigest()
            )
            self.assertEqual(result[0]["licenses"], [{"expression": "GPL-3.0-only"}])

    def test_missing_duplicate_and_wrong_version_candidate_are_rejected(self):
        self.assertTrue(hasattr(edge_inventory, "wheel_components"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate"
            dependencies = root / "deps"
            self.wheel(dependencies, "aethron-edge", "0.1.0", "old")
            with self.assertRaises(ValueError):
                edge_inventory.wheel_components(candidate, dependencies, {"aethron-edge": "0.1.0"})
            wrong = self.wheel(candidate, "aethron-edge", "0.2.0", "wrong")
            with self.assertRaises(ValueError):
                edge_inventory.wheel_components(candidate, dependencies, {"aethron-edge": "0.1.0"})
            wrong.unlink()
            self.wheel(candidate, "aethron-edge", "0.1.0", "new")
            self.wheel(candidate, "aethron-edge", "0.1.0", "other")
            with self.assertRaises(ValueError):
                edge_inventory.wheel_components(candidate, dependencies, {"aethron-edge": "0.1.0"})

    def test_lock_and_distribution_name_normalization_agree(self):
        self.assertTrue(hasattr(edge_inventory, "wheel_components"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.wheel(root / "deps", "typing_extensions", "4.16.0", "current")
            result = edge_inventory.wheel_components(
                root / "candidate", root / "deps", {"typing-extensions": "4.16.0"}
            )
            self.assertEqual(result[0]["name"], "typing-extensions")
            with self.assertRaises(ValueError):
                edge_inventory.wheel_components(
                    root / "candidate",
                    root / "deps",
                    {"typing_extensions": "3.0.0", "typing-extensions": "4.16.0"},
                )
            result = edge_inventory.wheel_components(
                root / "candidate", root / "deps", {"typing_extensions": "4.16.0"}
            )
            self.assertEqual(result[0]["name"], "typing-extensions")
