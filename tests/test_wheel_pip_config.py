"""Package payloads must not configure future installer invocations."""

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


class WheelPipConfig(unittest.TestCase):
    def test_installer_config_rejects_before_payload_reads(self):
        for package in ("aethron", "aethron_edge"):
            for target in ("pip.conf", "pip.ini", "PIP.CONF", "Pip.Ini"):
                for suffix in ("", "/", "/child"):
                    with self.subTest(package=package, target=target, suffix=suffix):
                        raw, payload = wheel_bytes(
                            package,
                            {f"{package}-0.2.0.data/data/{target}{suffix}": b"# fixture\n"},
                        )
                        with patch.object(
                            zipfile.ZipFile, "read", autospec=True, side_effect=zipfile.ZipFile.read
                        ) as read:
                            with self.assertRaisesRegex(
                                ValueError, "^wheel_source_payload_mismatch$"
                            ):
                                package_check.validate_source_payload(raw, payload, package)
                            read.assert_not_called()

    def test_nested_examples_and_non_config_resources_pass(self):
        for package in ("aethron", "aethron_edge"):
            with self.subTest(package=package):
                raw, payload = wheel_bytes(
                    package,
                    {
                        f"{package}/pip.conf": b"example\n",
                        f"{package}-0.2.0.data/purelib/pip.ini": b"example\n",
                        f"{package}-0.2.0.data/data/share/pip.conf": b"example\n",
                        f"{package}-0.2.0.data/data/pip.ini.txt": b"example\n",
                    },
                )
                package_check.validate_source_payload(raw, payload, package)

    def test_real_install_changes_isolated_pip_configuration(self):
        # Only a harmless timeout setting, local wheel and disposable venv.
        # The second pip invocation queries configuration; it makes no request.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            config_name = "pip.ini" if os.name == "nt" else "pip.conf"
            config = environment / config_name
            config.write_text("[global]\ntimeout = 19\n", encoding="utf-8")
            env = {key: value for key, value in os.environ.items() if not key.startswith("PIP_")}
            env["PIP_CONFIG_FILE"] = str(root / "absent-config")
            pip = [str(python), "-I", "-m", "pip", "--isolated", "--disable-pip-version-check"]

            def timeout_setting():
                return subprocess.run(
                    pip + ["config", "--site", "get", "global.timeout"],
                    cwd=root,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                ).stdout.strip()

            self.assertEqual(timeout_setting(), "19")
            replacement = b"[global]\ntimeout = 7\n"
            raw, payload = wheel_bytes(
                "aethron_edge", {f"aethron_edge-0.2.0.data/data/{config_name}": replacement}
            )
            wheel = root / "aethron_edge-0.2.0-py3-none-any.whl"
            wheel.write_bytes(raw)
            subprocess.run(
                pip + ["install", "--no-index", "--no-deps", "--no-compile", str(wheel)],
                cwd=root,
                env=env,
                check=True,
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(config.read_bytes(), replacement)
            self.assertEqual(timeout_setting(), "7")
            site = subprocess.run(
                [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            ).stdout.strip()
            self.assertEqual(
                package_check.snapshot_source_payload(Path(site), "aethron_edge"), payload
            )
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload, "aethron_edge")
