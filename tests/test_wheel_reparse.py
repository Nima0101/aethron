"""Wheel evidence rejects Windows redirects, including after consumers finish."""

import contextlib
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_core_package_inventory as core_inventory
import test_core_package_report as core_report
import test_edge_package_input_evidence as edge_report
import test_edge_package_inventory as edge_inventory

from scripts import edge_package_check, package_check


@contextlib.contextmanager
def redirected_path(target, attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT):
    # Model Windows metadata on Linux; this is not native junction qualification.
    original = Path.lstat

    def inspect(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path == target.get("path"):
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=attributes)
        return info

    with patch.object(Path, "lstat", inspect):
        yield


class WheelReparseTests(unittest.TestCase):
    def test_redirects_reject_before_payload_reads_in_both_builds(self):
        core = "aethron-0.2.0-py3-none-any.whl"
        edge = "aethron_edge-0.1.0-py3-none-any.whl"
        for checker, inventory, reason in (
            (core_inventory.CorePackageInventory(), {core: b"unread"}, "wheel_artifacts_changed"),
            (
                edge_inventory.PackageEvidenceInventory(),
                {core: b"unread", edge: b"unread"},
                "package_artifact_changed",
            ),
        ):
            for lane in ("a", "b"):
                for entry in ("", *inventory):
                    with self.subTest(checker=type(checker).__name__, lane=lane, entry=entry):
                        target = {}

                        def mutate(root, target=target, lane=lane, entry=entry):
                            target["path"] = root / lane / entry

                        with redirected_path(target):
                            error = checker.compare(inventory, inventory, mutate=mutate)
                        self.assertIsInstance(error, ValueError)
                        self.assertEqual(str(error), reason)

    def test_core_post_consumer_redirect_cannot_publish_success(self):
        for lane in ("a", "b"):
            for directory in (False, True):
                with self.subTest(lane=lane, directory=directory):
                    target = {}
                    builds = {}

                    def on_call(args, target=target, builds=builds, lane=lane, directory=directory):
                        if "--outdir" in args:
                            build = Path(args[args.index("--outdir") + 1])
                            builds[build.name] = build
                        if args[1:5] == ["-I", "-m", "aethron", "replay"]:
                            target["path"] = builds[lane]
                            if not directory:
                                target["path"] /= "aethron-0.2.0-py3-none-any.whl"

                    with (
                        core_report.CorePackageReport().fixture(on_call=on_call) as fixture,
                        redirected_path(target),
                    ):
                        with self.assertRaisesRegex(ValueError, "wheel_artifacts_changed"):
                            package_check.run()
                        self.assertEqual(fixture[0].getvalue(), "")

    def test_edge_post_consumer_redirect_cannot_publish_success(self):
        for lane in ("a", "b"):
            for entry in (
                "",
                "aethron-0.2.0-py3-none-any.whl",
                "aethron_edge-0.1.0-py3-none-any.whl",
            ):
                with self.subTest(lane=lane, entry=entry):
                    target = {}
                    builds = {}

                    def on_run(args, target=target, builds=builds, lane=lane, entry=entry):
                        if "--outdir" in args:
                            build = Path(args[args.index("--outdir") + 1])
                            builds[build.name] = build
                        if any(str(arg).endswith("observe.py") for arg in args):
                            target["path"] = builds[lane] / entry

                    def on_exit(output, printed):
                        self.assertFalse((output / "result.json").exists())
                        self.assertEqual(printed.getvalue(), "")

                    with redirected_path(target):
                        with self.assertRaisesRegex(ValueError, "package_artifact_changed"):
                            edge_report.PackageInputEvidence().probe(on_run=on_run, on_exit=on_exit)

    def test_ordinary_windows_attributes_preserve_wheel_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wheel = root / "aethron-0.2.0-py3-none-any.whl"
            wheel.write_bytes(b"ordinary wheel")
            for path in (root, wheel):
                with (
                    self.subTest(path=path.name),
                    redirected_path(
                        {"path": path}, stat.FILE_ATTRIBUTE_ARCHIVE | stat.FILE_ATTRIBUTE_READONLY
                    ),
                ):
                    self.assertEqual(package_check.wheel_paths(root), [wheel])
                    self.assertEqual(edge_package_check.wheel_inventory(root), {wheel.name: wheel})
