"""Wheels must not replace the installer-owned virtual environment config."""

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


class WheelVenvConfig(unittest.TestCase):
    def test_environment_config_rejects_before_payload_reads(self):
        for package in ("aethron", "aethron_edge"):
            for target in ("pyvenv.cfg", "PYVENV.CFG", "PyVenv.Cfg", "pyvenv.cfg/child"):
                with self.subTest(package=package, target=target):
                    raw, payload = wheel_bytes(
                        package, {f"{package}-0.2.0.data/data/{target}": b"inert fixture\n"}
                    )
                    with patch.object(
                        zipfile.ZipFile, "read", autospec=True, side_effect=zipfile.ZipFile.read
                    ) as read:
                        with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                            package_check.validate_source_payload(raw, payload, package)
                        read.assert_not_called()

    def test_non_environment_config_resources_pass(self):
        for package in ("aethron", "aethron_edge"):
            with self.subTest(package=package):
                raw, payload = wheel_bytes(
                    package,
                    {
                        f"{package}/pyvenv.cfg": b"example\n",
                        f"{package}-0.2.0.data/purelib/pyvenv.cfg": b"example\n",
                        f"{package}-0.2.0.data/data/share/pyvenv.cfg": b"example\n",
                        f"{package}-0.2.0.data/data/pyvenv.cfg.txt": b"example\n",
                    },
                )
                package_check.validate_source_payload(raw, payload, package)

    def test_installer_overwrites_environment_config_outside_source_manifest(self):
        # Inert fixture in a disposable venv. Do not execute the environment's
        # interpreter after replacement: inspecting the bytes proves the write.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            result = subprocess.run(
                [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            site = Path(result.stdout.strip())
            config = environment / "pyvenv.cfg"
            original = config.read_bytes()
            replacement = b"# inert package fixture\n"
            raw, payload = wheel_bytes(
                "aethron_edge", {"aethron_edge-0.2.0.data/data/pyvenv.cfg": replacement}
            )
            wheel = root / "aethron_edge-0.2.0-py3-none-any.whl"
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
            self.assertNotEqual(original, replacement)
            self.assertEqual(config.read_bytes(), replacement)
            self.assertEqual(package_check.snapshot_source_payload(site, "aethron_edge"), payload)
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload, "aethron_edge")
