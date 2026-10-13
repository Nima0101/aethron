"""Consumer success cannot qualify wheels changed after their comparison."""

import contextlib
import hashlib
import io
import json
import subprocess
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import package_check


class PackageFinalIntegrityTests(unittest.TestCase):
    def run_checker(self, lane=None, mutation=None):
        output = io.StringIO()
        builds = {}
        wheel_name = "aethron-0.2.0-py3-none-any.whl"
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as wheel:
            for name, data in package_check.snapshot_source_payload(package_check.ROOT).items():
                wheel.writestr(name, data)
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
                pass
            elif args[1:] == ["--help"]:
                return subprocess.CompletedProcess(args, 0, stdout="usage: aethron")
            elif args[1:5] == ["-I", "-m", "aethron", "demo"]:
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
                row = {"tracks": [{"id": "fixture", "sources": ["depth", "lwir", "radar"]}]}
                return subprocess.CompletedProcess(
                    args, 0, stdout="\n".join([json.dumps(row)] * 24)
                )
            else:
                self.fail(f"unexpected process: {args}")
            return subprocess.CompletedProcess(args, 0)

        with (
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

    def test_unchanged_artifacts_retain_compared_digest(self):
        self.run_checker()

    def test_consumer_time_artifact_changes_prevent_success(self):
        for lane in ("a", "b"):
            for mutation in ("changed", "missing", "extra", "renamed"):
                with self.subTest(lane=lane, mutation=mutation):
                    self.run_checker(lane, mutation)
