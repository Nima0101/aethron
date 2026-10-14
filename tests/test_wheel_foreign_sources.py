"""Wheel source parity must cover every installed Python source package."""

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


class WheelForeignSources(unittest.TestCase):
    def test_foreign_sources_reject_before_payload_reads(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for name in (
                    "foreign.py",
                    "foreign/__init__.py",
                    "foreign/namespace/module.py",
                    "FOREIGN/MODULE.PY",
                    f"{package}_extra/module.py",
                    "aethron/module.py" if package == "aethron_edge" else "aethron_edge/module.py",
                ):
                    with self.subTest(package=package, layout=layout, name=name):
                        raw, payload = wheel_bytes(package, {layout + name: b"VALUE = 2\n"})
                        with patch.object(
                            zipfile.ZipFile, "read", autospec=True, side_effect=zipfile.ZipFile.read
                        ) as read:
                            with self.assertRaisesRegex(
                                ValueError, "^wheel_source_payload_mismatch$"
                            ):
                                package_check.validate_source_payload(raw, payload, package)
                            read.assert_not_called()

    def test_nonimport_resources_and_declared_sources_pass(self):
        for package in ("aethron", "aethron_edge"):
            with self.subTest(package=package):
                raw, payload = wheel_bytes(
                    package,
                    {
                        f"{package}-0.2.0.dist-info/licenses/example.py": b"# license example\n",
                        f"{package}-0.2.0.data/data/share/example.py": b"# data example\n",
                        f"{package}-0.2.0.data/headers/example.py": b"# header example\n",
                        "foreign/module.py.txt": b"documentation\n",
                        "foreign.py/notes.txt": b"documentation\n",
                    },
                )
                package_check.validate_source_payload(raw, payload, package)

    def test_installer_overwrites_foreign_source_outside_verified_package(self):
        # Only inert bytes in a disposable environment. The overwritten package
        # is never imported, and no installed tooling or startup hook is changed.
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
            foreign = site / "aethron/module.py"
            foreign.parent.mkdir()
            foreign.write_bytes(b"VALUE = 1\n")
            raw, payload = wheel_bytes("aethron_edge", {"aethron/module.py": b"VALUE = 2\n"})
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
            self.assertEqual(foreign.read_bytes(), b"VALUE = 2\n")
            self.assertEqual(package_check.snapshot_source_payload(site, "aethron_edge"), payload)
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload, "aethron_edge")
