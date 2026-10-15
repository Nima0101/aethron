"""Core reproducibility evidence needs exactly one matching wheel per build."""

import contextlib
import io
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import package_check


class CorePackageInventory(unittest.TestCase):
    wheel = "aethron-0.2.0-py3-none-any.whl"

    def compare(self, first, second, *, mutate=None):
        workspace = package_check.reproduction_workspace
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            read_bytes = Path.read_bytes

            def checked_read(path):
                if mutate is not None and path.suffix == ".whl":
                    self.fail("wheel payload read before malformed inventory rejection")
                return read_bytes(path)

            def fake_process(args, **kwargs):
                if "build" in args:
                    destination = Path(args[args.index("--outdir") + 1])
                    destination.mkdir()
                    inventory = first if destination.name == "a" else second
                    for name, data in inventory.items():
                        (destination / name).write_bytes(data)
                    if mutate is not None and destination.name == "b":
                        mutate(destination.parent)
                    return subprocess.CompletedProcess(args, 0)
                self.assertEqual(args[1:3], ["-m", "venv"])
                raise RuntimeError("inventory_accepted")

            with (
                patch.object(
                    package_check,
                    "reproduction_workspace",
                    side_effect=lambda **kwargs: workspace(dir=directory, **kwargs),
                ),
                patch.object(package_check.subprocess, "run", side_effect=fake_process),
                patch.object(Path, "read_bytes", checked_read),
                contextlib.redirect_stdout(output),
            ):
                try:
                    package_check.run()
                except Exception as error:
                    self.assertEqual(output.getvalue(), "")
                    return error
            self.fail("probe unexpectedly completed the package workflow")

    def assert_rejected(self, first, second):
        error = self.compare(first, second)
        self.assertIsInstance(error, ValueError)
        self.assertEqual(str(error), "wheel_inventory_mismatch")

    def test_missing_wheels_are_rejected(self):
        single = {self.wheel: b"synthetic"}
        for first, second in (({}, {}), ({}, single), (single, {})):
            with self.subTest(first=first, second=second):
                self.assert_rejected(first, second)

    def test_extra_wheels_are_rejected_in_either_or_both_builds(self):
        single = {self.wheel: b"synthetic"}
        extra = dict(single, **{"additional-1.0-py3-none-any.whl": b"synthetic"})
        for first, second in ((single, extra), (extra, single), (extra, extra)):
            with self.subTest(first=first, second=second):
                self.assert_rejected(first, second)

    def test_renamed_wheel_is_rejected_even_with_identical_bytes(self):
        self.assert_rejected(
            {self.wheel: b"synthetic"}, {"aethron-0.3.0-py3-none-any.whl": b"synthetic"}
        )

    def test_changed_bytes_remain_rejected(self):
        error = self.compare({self.wheel: b"original"}, {self.wheel: b"changed"})
        self.assertIsInstance(error, AssertionError)
        self.assertEqual(str(error), "wheel builds differ")

    def test_equal_single_wheels_reach_consumer_boundary(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as wheel:
            wheel.writestr(
                "aethron-0.2.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: aethron\nVersion: 0.2.0\nRequires-Python: >=3.9\n",
            )
            for name, data in package_check.snapshot_source_payload(package_check.ROOT).items():
                wheel.writestr(name, data)
        inventory = {self.wheel: archive.getvalue()}
        error = self.compare(inventory, inventory)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(str(error), "inventory_accepted")

    def test_invalid_artifacts_reject_before_either_wheel_is_read(self):
        inventory = {self.wheel: b"unread candidate"}
        mutations = ["linked_wheel", "linked_directory", "directory"]
        if hasattr(os, "mkfifo"):
            mutations.append("fifo")
        for lane in ("a", "b"):
            for mutation in mutations:
                with self.subTest(lane=lane, mutation=mutation):

                    def mutate(root, lane=lane, mutation=mutation):
                        build = root / lane
                        wheel = build / self.wheel
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
                    self.assertEqual(str(error), "wheel_artifacts_changed")
