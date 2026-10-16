"""Release evidence must reject redirected artifacts at every observation boundary."""

import contextlib
import hashlib
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_reproduce_report as report
from test_package_source_links import windows_attributes

from scripts import reproduce


class ReleaseReparseTests(unittest.TestCase):
    def test_reparse_inventory_rejects_before_traversal_or_payload_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {}
            for name in reproduce.RELEASE_ARTIFACTS:
                (root / name).write_bytes(b"unread artifact")
                manifest[name] = hashlib.sha256(b"unread artifact").hexdigest()
            for entry in ("", *sorted(manifest)):
                with self.subTest(entry=entry), contextlib.ExitStack() as stack:
                    stack.enter_context(
                        windows_attributes(root / entry, stat.FILE_ATTRIBUTE_REPARSE_POINT)
                    )
                    read = stack.enter_context(
                        patch.object(
                            Path,
                            "read_bytes",
                            side_effect=AssertionError("unadmitted artifact read"),
                        )
                    )
                    if not entry:
                        walk = stack.enter_context(patch.object(Path, "iterdir"))
                    with self.assertRaisesRegex(ValueError, "^release_artifacts_changed$"):
                        reproduce.validate_artifacts(root, manifest)
                    read.assert_not_called()
                    if not entry:
                        walk.assert_not_called()

    def test_reparse_build_and_post_consumer_outputs_cannot_publish_success(self):
        for lane in ("a", "b"):
            for entry in ("", *sorted(reproduce.RELEASE_ARTIFACTS)):
                for stage in (0, 1, 2):
                    with self.subTest(lane=lane, entry=entry, stage=stage):
                        with contextlib.ExitStack() as stack:
                            consumers_seen = []

                            def child(
                                args,
                                kwargs,
                                workspace,
                                stage=stage,
                                lane=lane,
                                entry=entry,
                                consumers_seen=consumers_seen,
                            ):
                                build_b = (
                                    args[1:2] == ["scripts/release.py"]
                                    and Path(args[-1]).name == "b"
                                )
                                consumer = args[1:2] == ["-I"]
                                if consumer:
                                    consumers_seen.append(args)
                                if (stage == 0 and build_b) or (
                                    stage > 0 and consumer and len(consumers_seen) == stage
                                ):
                                    stack.enter_context(
                                        windows_attributes(
                                            workspace / lane / entry,
                                            stat.FILE_ATTRIBUTE_REPARSE_POINT,
                                        )
                                    )

                            output, error, consumers, _, _ = report.ReproductionReport().invoke(
                                python_child=child, check_workspace=True
                            )
                        self.assertIsInstance(error, ValueError)
                        self.assertEqual(str(error), "release_artifacts_changed")
                        self.assertEqual(output, "")
                        self.assertEqual(len(consumers), stage)

    def test_ordinary_windows_attributes_preserve_real_consumer_success(self):
        for lane in ("a", "b"):
            for entry in ("", "aethron.pyz"):
                with self.subTest(lane=lane, entry=entry), contextlib.ExitStack() as stack:

                    def child(args, kwargs, workspace, lane=lane, entry=entry):
                        if args[1:2] == ["scripts/release.py"] and Path(args[-1]).name == "b":
                            stack.enter_context(
                                windows_attributes(
                                    workspace / lane / entry,
                                    stat.FILE_ATTRIBUTE_ARCHIVE | stat.FILE_ATTRIBUTE_READONLY,
                                )
                            )

                    output, error, consumers, _, _ = report.ReproductionReport().invoke(
                        python_child=child, real_consumers=True, check_workspace=True
                    )
                    self.assertIsNone(error)
                    self.assertIn('"byte_identical_builds": true', output)
                    self.assertEqual(len(consumers), 2)
