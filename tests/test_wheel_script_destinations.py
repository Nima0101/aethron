"""Source-wheel admission must not install undeclared script payloads."""

import os
import subprocess
import tempfile
import unittest
import venv
import zipfile
from pathlib import Path
from unittest.mock import patch

from test_wheel_data_destinations import wheel_bytes

from scripts import package_check


class WheelScriptDestinations(unittest.TestCase):
    def test_script_destinations_reject_before_source_reads(self):
        for package in ("aethron", "aethron_edge"):
            for location in ("scripts", "data/bin", "data/Scripts", "data/BIN", "data/scripts"):
                for target in ("fixture-tool", "fixture.py", "fixture.exe", "nested/tool", ""):
                    with self.subTest(package=package, location=location, target=target):
                        raw, payload = wheel_bytes(
                            package,
                            {f"{package}-0.2.0.data/{location}/{target}": b"# inert fixture\n"},
                        )
                        with patch.object(
                            zipfile.ZipFile, "read", autospec=True, side_effect=zipfile.ZipFile.read
                        ) as read:
                            with self.assertRaisesRegex(
                                ValueError, "^wheel_source_payload_mismatch$"
                            ):
                                package_check.validate_source_payload(raw, payload, package)
                            read.assert_not_called()

    def test_resources_named_scripts_or_bin_remain_allowed(self):
        for package in ("aethron", "aethron_edge"):
            with self.subTest(package=package):
                raw, payload = wheel_bytes(
                    package,
                    {
                        f"{package}/scripts/example.txt": b"example\n",
                        f"{package}-0.2.0.data/data/share/bin/example.txt": b"example\n",
                        f"{package}-0.2.0.data/data/share/scripts/example.py": b"# example\n",
                        f"{package}-0.2.0.data/data/bin.txt": b"example\n",
                    },
                )
                package_check.validate_source_payload(raw, payload, package)

    def test_real_installer_spreads_both_script_layouts_outside_source_manifest(self):
        # Only create inert, uniquely named files in a disposable environment.
        # Never replace or execute an interpreter, pip, or an existing launcher.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            scripts = environment / ("Scripts" if os.name == "nt" else "bin")
            python = scripts / ("python.exe" if os.name == "nt" else "python")
            raw, payload = wheel_bytes(
                "aethron",
                {
                    "aethron-0.2.0.data/scripts/aethron-fixture-script.txt": b"# inert script\n",
                    f"aethron-0.2.0.data/data/{scripts.name}/aethron-fixture-data.txt": b"# inert data\n",
                },
            )
            wheel = root / "aethron-0.2.0-py3-none-any.whl"
            wheel.write_bytes(raw)
            subprocess.run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "pip",
                    "--isolated",
                    "--disable-pip-version-check",
                    "install",
                    "--no-index",
                    "--no-deps",
                    "--no-compile",
                    str(wheel),
                ],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(
                (scripts / "aethron-fixture-script.txt").read_bytes(), b"# inert script\n"
            )
            self.assertEqual((scripts / "aethron-fixture-data.txt").read_bytes(), b"# inert data\n")
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload)
