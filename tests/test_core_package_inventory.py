"""Core reproducibility evidence needs exactly one matching wheel per build."""

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import package_check


class CorePackageInventory(unittest.TestCase):
    wheel = "aethron-0.2.0-py3-none-any.whl"

    def compare(self, first, second):
        make_directory = tempfile.TemporaryDirectory
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()

            def fake_process(args, **kwargs):
                if "build" in args:
                    destination = Path(args[args.index("--outdir") + 1])
                    destination.mkdir()
                    inventory = first if destination.name == "a" else second
                    for name, data in inventory.items():
                        (destination / name).write_bytes(data)
                    return subprocess.CompletedProcess(args, 0)
                self.assertEqual(args[1:3], ["-m", "venv"])
                raise RuntimeError("inventory_accepted")

            with (
                patch.object(
                    package_check.tempfile,
                    "TemporaryDirectory",
                    side_effect=lambda **kwargs: make_directory(dir=directory, **kwargs),
                ),
                patch.object(package_check.subprocess, "run", side_effect=fake_process),
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
        inventory = {self.wheel: b"synthetic"}
        error = self.compare(inventory, inventory)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(str(error), "inventory_accepted")
