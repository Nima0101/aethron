"""Reproducibility evidence requires complete, nonempty wheel inventories."""

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import edge_package_check, package_check


class PackageEvidenceInventory(unittest.TestCase):
    def compare(self, first, second, *, mutate=None):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "attempt"
            read_bytes = Path.read_bytes
            builds = 0

            def checked_read(path):
                if mutate is not None and path.suffix == ".whl":
                    self.fail("wheel payload read before malformed inventory rejection")
                return read_bytes(path)

            def fake_build(args, **kwargs):
                nonlocal builds
                if "build" in args:
                    destination = Path(args[args.index("--outdir") + 1])
                    destination.mkdir(exist_ok=True)
                    inventory = first if destination.name == "a" else second
                    for name, data in inventory.items():
                        (destination / name).write_bytes(data)
                    builds += 1
                    if mutate is not None and builds == 4:
                        mutate(output)
                    return subprocess.CompletedProcess(args, 0)
                raise RuntimeError("inventory_accepted")

            with (
                patch.object(edge_package_check.subprocess, "run", side_effect=fake_build),
                patch.object(package_check, "validate_source_payload"),
                patch.object(Path, "read_bytes", checked_read),
            ):
                try:
                    edge_package_check.run(Path(directory) / "wheelhouse", output)
                except Exception as error:
                    self.assertFalse((output / "result.json").exists())
                    return error
            self.fail("probe unexpectedly completed the package workflow")

    def test_invalid_artifacts_reject_before_any_wheel_is_read(self):
        inventory = {
            "aethron-0.2.0-py3-none-any.whl": b"core",
            "aethron_edge-0.1.0-py3-none-any.whl": b"edge",
        }
        mutations = ["linked_wheel", "linked_directory", "directory"]
        if hasattr(os, "mkfifo"):
            mutations.append("fifo")
        for lane in ("a", "b"):
            for name in inventory:
                for mutation in mutations:
                    with self.subTest(lane=lane, name=name, mutation=mutation):

                        def mutate(root, lane=lane, name=name, mutation=mutation):
                            build = root / lane
                            wheel = build / name
                            if mutation == "linked_directory":
                                target = root / "external-build"
                                build.rename(target)
                                build.symlink_to(target, target_is_directory=True)
                            elif mutation == "linked_wheel":
                                target = root / "external-wheel"
                                wheel.rename(target)
                                wheel.symlink_to(target)
                            else:
                                wheel.unlink()
                                if mutation == "directory":
                                    wheel.mkdir()
                                else:
                                    os.mkfifo(wheel)

                        error = self.compare(inventory, inventory, mutate=mutate)
                        self.assertIsInstance(error, ValueError)
                        self.assertEqual(str(error), "package_artifact_changed")

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
