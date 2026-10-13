"""Equal wheels must also match the selected source payload captured before build."""

import contextlib
import io
import subprocess
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import package_check


class CorePackagePayload(unittest.TestCase):
    def check_payload(self, defect=None, mutate_source=False):
        payload = {
            "aethron/__init__.py": b"# current source\n",
            "aethron/models/rules.json": b'{"synthetic":true}\n',
            "aethron/_bounds.pxd": b"# current declaration\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, data in payload.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            wheel = io.BytesIO()
            records = list(payload.items())
            if defect == "changed":
                records[0] = (records[0][0], b"# stale source\n")
            elif defect == "missing":
                records.pop()
            elif defect == "extra":
                records.append(("aethron/retired.py", b"# stale extra file\n"))
            elif defect == "duplicate":
                records.append(records[0])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(wheel, "w") as archive:
                    for name, data in records:
                        archive.writestr(name, data)
                    archive.writestr(
                        "aethron/_bounds.synthetic.so", b"not covered by source parity"
                    )
            calls = []

            def process(args, **kwargs):
                calls.append(args)
                if args[1:4] == ["-m", "build", "--no-isolation"]:
                    destination = Path(args[args.index("--outdir") + 1])
                    destination.mkdir()
                    (destination / "aethron-0.2.0-py3-none-any.whl").write_bytes(wheel.getvalue())
                    if mutate_source:
                        (root / "aethron/__init__.py").write_bytes(b"# replaced during build\n")
                    return subprocess.CompletedProcess(args, 0)
                raise RuntimeError("consumer_boundary")

            output = io.StringIO()
            with (
                patch.object(package_check, "ROOT", root),
                patch.object(package_check.subprocess, "run", side_effect=process),
                contextlib.redirect_stdout(output),
            ):
                if defect:
                    with self.assertRaises(Exception) as raised:
                        package_check.run()
                    self.assertIsInstance(raised.exception, ValueError)
                    self.assertEqual(str(raised.exception), "wheel_source_payload_mismatch")
                    self.assertEqual(len(calls), 2, "reject before environment/install/consumer")
                else:
                    with self.assertRaisesRegex(RuntimeError, "consumer_boundary"):
                        package_check.run()
                    self.assertEqual(len(calls), 3)
            self.assertEqual(output.getvalue(), "")

    def test_identical_stale_or_incomplete_wheels_are_rejected(self):
        for defect in ("changed", "missing", "extra", "duplicate"):
            with self.subTest(defect=defect):
                self.check_payload(defect)

    def test_matching_payload_reaches_consumer(self):
        self.check_payload()

    def test_comparison_uses_prebuild_snapshot(self):
        self.check_payload(mutate_source=True)

    def test_empty_or_nonfile_source_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "empty_source_payload"):
                package_check.snapshot_source_payload(root)
            (root / "aethron/fake.py").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "invalid_source_payload_file"):
                package_check.snapshot_source_payload(root)

    def test_symlinked_source_directories_are_rejected(self):
        for location in ("aethron", "aethron/models"):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "source"
                target = Path(directory) / "external"
                target.mkdir()
                (target / "rules.json").write_bytes(b"{}")
                link = root / location
                link.parent.mkdir(parents=True)
                link.symlink_to(target, target_is_directory=True)
                if location != "aethron":
                    (root / "aethron/__init__.py").write_bytes(b"")
                with self.assertRaisesRegex(ValueError, "invalid_source_payload_file"):
                    package_check.snapshot_source_payload(root)
