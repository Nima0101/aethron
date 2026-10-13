"""Reproducibility evidence requires complete, nonempty wheel inventories."""

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import edge_package_check


class PackageEvidenceInventory(unittest.TestCase):
    def compare(self, first, second):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "attempt"

            def fake_build(args, **kwargs):
                if "build" in args:
                    destination = Path(args[args.index("--outdir") + 1])
                    destination.mkdir(exist_ok=True)
                    inventory = first if destination.name == "a" else second
                    for name, data in inventory.items():
                        (destination / name).write_bytes(data)
                    return subprocess.CompletedProcess(args, 0)
                raise RuntimeError("inventory_accepted")

            with patch.object(edge_package_check.subprocess, "run", side_effect=fake_build):
                try:
                    edge_package_check.run(Path(directory) / "wheelhouse", output)
                except Exception as error:
                    self.assertFalse((output / "result.json").exists())
                    return error
            self.fail("probe unexpectedly completed the package workflow")

    def assert_inventory_rejected(self, first, second):
        error = self.compare(first, second)
        self.assertIsInstance(error, ValueError)
        self.assertEqual(str(error), "wheel_inventory_mismatch")

    def test_empty_build_cannot_establish_reproducibility(self):
        for first, second in (({}, {}), ({}, {"aethron-0.2.0-py3-none-any.whl": b"core"})):
            with self.subTest(first=first, second=second):
                self.assert_inventory_rejected(first, second)

    def test_missing_or_extra_wheel_is_rejected(self):
        complete = {
            "aethron-0.2.0-py3-none-any.whl": b"core",
            "aethron_edge-0.1.0-py3-none-any.whl": b"edge",
        }
        incomplete = {"aethron-0.2.0-py3-none-any.whl": b"core"}
        for first, second in ((complete, incomplete), (incomplete, complete)):
            with self.subTest(first=first, second=second):
                self.assert_inventory_rejected(first, second)

    @unittest.skipUnless(importlib.util.find_spec("packaging.utils"), "wheel build dependency")
    def test_changed_bytes_are_rejected(self):
        first = {
            "aethron-0.2.0-py3-none-any.whl": b"original",
            "aethron_edge-0.1.0-py3-none-any.whl": b"edge",
        }
        second = dict(first, **{"aethron-0.2.0-py3-none-any.whl": b"changed"})
        error = self.compare(first, second)
        self.assertIsInstance(error, (AssertionError, ValueError))
        self.assertIn("nonreproducible", str(error))

    @unittest.skipUnless(importlib.util.find_spec("packaging.utils"), "wheel build dependency")
    def test_equal_inventory_reaches_installation_boundary(self):
        inventory = {
            "aethron-0.2.0-py3-none-any.whl": b"core",
            "aethron_edge-0.1.0-py3-none-any.whl": b"edge",
        }
        error = self.compare(inventory, inventory)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(str(error), "inventory_accepted")

    @unittest.skipUnless(importlib.util.find_spec("packaging.utils"), "wheel build dependency")
    def test_equal_but_incomplete_or_unexpected_distributions_are_rejected(self):
        core = "aethron-0.2.0-py3-none-any.whl"
        edge = "aethron_edge-0.1.0-py3-none-any.whl"
        for names in (
            (core,),
            (edge,),
            (core, "unrelated-0.1.0-py3-none-any.whl"),
            (core, edge, "unrelated-0.1.0-py3-none-any.whl"),
            (core, edge, "aethron-0.2.0-1-py3-none-any.whl"),
            (core, "invalid.whl"),
        ):
            with self.subTest(names=names):
                inventory = dict.fromkeys(names, b"synthetic-wheel")
                error = self.compare(inventory, inventory)
                self.assertIsInstance(error, ValueError)
                self.assertEqual(str(error), "wheel_distribution_mismatch")

    @unittest.skipUnless(importlib.util.find_spec("packaging.utils"), "wheel build dependency")
    def test_build_and_platform_tags_do_not_change_distribution_identity(self):
        inventory = {
            "aethron-0.2.0-1-cp311-cp311-linux_x86_64.whl": b"core",
            "aethron_edge-0.1.0-py3-none-any.whl": b"edge",
        }
        error = self.compare(inventory, inventory)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(str(error), "inventory_accepted")
