"""Consumer success cannot qualify wheels changed after their comparison."""

import contextlib
import csv
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import package_check
from tests.wheel_fixtures import record_row


class PackageFinalIntegrityTests(unittest.TestCase):
    def run_checker(self, lane=None, mutation=None):
        output = io.StringIO()
        builds = {}
        consumer_stages = []
        wheel_name = "aethron-0.2.0-py3-none-any.whl"
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as wheel:
            for name, data in package_check.snapshot_source_payload(package_check.ROOT).items():
                wheel.writestr(name, data)
            wheel.writestr(
                "aethron-0.2.0.dist-info/METADATA",
                "Metadata-Version: 2.4\nName: aethron\nVersion: 0.2.0\nRequires-Python: >=3.9\n"
                "License-Expression: GPL-3.0-only\n"
                "Provides-Extra: vision\nRequires-Dist: numpy==2.3.5; extra == 'vision'\n"
                "Requires-Dist: opencv-python-headless==4.13.0.92; extra == 'vision'\n",
            )
            wheel.writestr(
                "aethron-0.2.0.dist-info/WHEEL",
                "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
            wheel.writestr(
                "aethron-0.2.0.dist-info/entry_points.txt",
                "[console_scripts]\naethron = aethron.__main__:main\n",
            )
            record = io.StringIO(newline="")
            writer = csv.writer(record)
            for name in wheel.namelist():
                writer.writerow(record_row(name, wheel.read(name)))
            record_name = "aethron-0.2.0.dist-info/RECORD"
            writer.writerow((record_name, "", ""))
            wheel.writestr(record_name, record.getvalue())
        wheel_bytes = archive.getvalue()

        def process(args, **kwargs):
            if args[1:4] == ["-m", "build", "--no-isolation"]:
                destination = Path(args[args.index("--outdir") + 1])
                destination.mkdir()
                builds[destination.name] = destination
                (destination / wheel_name).write_bytes(wheel_bytes)
            elif args[1:3] == ["-m", "venv"]:
                pass
            elif args[1:4] == ["-m", "pip", "install"]:
                consumer_stages.append("install")
            elif args[1:] == ["-I", "-m", "pip", "check"]:
                consumer_stages.append("dependencies")
            elif args[1] == "-I" and args[-1] == "--installed-payload":
                consumer_stages.append("installed-payload")
                with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as wheel:
                    manifest = {
                        name: hashlib.sha256(wheel.read(name)).hexdigest()
                        for name in wheel.namelist()
                        if name.startswith("aethron/")
                    }
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(manifest))
            elif args[1:] == ["--help"]:
                consumer_stages.append("launcher")
                return subprocess.CompletedProcess(args, 0, stdout="usage: aethron")
            elif args[1:5] == ["-I", "-m", "aethron", "demo"]:
                consumer_stages.append("demo")
                row = {
                    "scenario": "person-zero-visible-thermal",
                    "result": {
                        "recommendation": {"action": "STOP"},
                        "claims": [{"capability": "human_presence", "sources": ["thermal_person"]}],
                    },
                }
                return subprocess.CompletedProcess(
                    args, 0, stdout="\n".join([json.dumps(row)] * 22)
                )
            elif args[1:5] == ["-I", "-m", "aethron", "replay"]:
                consumer_stages.append("replay")
                if mutation:
                    wheel = builds[lane] / wheel_name
                    if mutation == "changed":
                        wheel.write_bytes(b"unverified replacement")
                    elif mutation == "missing":
                        wheel.unlink()
                    elif mutation == "extra":
                        (builds[lane] / "extra.whl").write_bytes(wheel_bytes)
                    elif mutation == "renamed":
                        wheel.rename(builds[lane] / "renamed.whl")
                    elif mutation == "linked_wheel":
                        target = builds[lane].parent / "external-wheel"
                        wheel.rename(target)
                        wheel.symlink_to(target)
                    elif mutation == "linked_directory":
                        target = builds[lane].parent / "external-build"
                        builds[lane].rename(target)
                        builds[lane].symlink_to(target, target_is_directory=True)
                    else:
                        self.fail(f"unknown artifact mutation: {mutation}")
                row = {"tracks": [{"id": "fixture", "sources": ["depth", "lwir", "radar"]}]}
                return subprocess.CompletedProcess(
                    args, 0, stdout="\n".join([json.dumps(row)] * 24)
                )
            else:
                self.fail(f"unexpected process: {args}")
            return subprocess.CompletedProcess(args, 0)

        with (
            tempfile.TemporaryDirectory() as sandbox,
            patch.object(tempfile, "tempdir", sandbox),
            patch.object(package_check.subprocess, "run", side_effect=process),
            contextlib.redirect_stdout(output),
        ):
            if mutation:
                with self.assertRaisesRegex(ValueError, "wheel_artifacts_changed"):
                    package_check.run()
                self.assertEqual(output.getvalue(), "")
            else:
                package_check.run()
                report = json.loads(output.getvalue())
                self.assertEqual(report["sha256"], hashlib.sha256(wheel_bytes).hexdigest())
                self.assertIs(report["byte_identical"], True)
            self.assertEqual(
                consumer_stages,
                [
                    "install",
                    "dependencies",
                    "installed-payload",
                    "launcher",
                    "demo",
                    "replay",
                    "installed-payload",
                ],
            )

    def test_unchanged_artifacts_retain_compared_digest(self):
        self.run_checker()

    def test_consumer_time_artifact_changes_prevent_success(self):
        for lane in ("a", "b"):
            for mutation in (
                "changed",
                "missing",
                "extra",
                "renamed",
                "linked_wheel",
                "linked_directory",
            ):
                with self.subTest(lane=lane, mutation=mutation):
                    self.run_checker(lane, mutation)
