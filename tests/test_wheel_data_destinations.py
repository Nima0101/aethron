"""Data-scheme records must not bypass import-destination admission."""

import csv
import io
import os
import subprocess
import tempfile
import unittest
import venv
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import package_check


def wheel_bytes(package, extras):
    payload = {f"{package}/module.py": b"VALUE = 1\n"}
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as wheel:
        for name, data in list(payload.items()) + list(extras.items()):
            wheel.writestr(name, data)
        metadata = f"{package}-0.2.0.dist-info/"
        wheel.writestr(
            metadata + "METADATA",
            f"Metadata-Version: 2.1\nName: {package}\nVersion: 0.2.0\n",
        )
        wheel.writestr(
            metadata + "WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        record = io.StringIO(newline="")
        csv.writer(record).writerows(
            (member.filename, "", "") for member in wheel.infolist() if not member.is_dir()
        )
        csv.writer(record).writerow((metadata + "RECORD", "", ""))
        wheel.writestr(metadata + "RECORD", record.getvalue())
    return archive.getvalue(), payload


class WheelDataDestinations(unittest.TestCase):
    def test_data_scheme_import_directories_reject_before_member_reads(self):
        for package in ("aethron", "aethron_edge"):
            for directory in (
                "lib/python3.9/site-packages",
                "lib64/python3.13/site-packages",
                "lib/python3.13t/site-packages",
                "local/lib/python3.13/dist-packages",
                "Lib/site-packages",
                "LIB/SITE-PACKAGES",
            ):
                for target in (f"{package}/module.py", "fixture.pth", "sitecustomize.py", ""):
                    with self.subTest(package=package, directory=directory, target=target):
                        raw, payload = wheel_bytes(
                            package,
                            {f"{package}-0.2.0.data/data/{directory}/{target}": b"# fixture\n"},
                        )
                        with patch.object(
                            zipfile.ZipFile, "read", autospec=True, side_effect=zipfile.ZipFile.read
                        ) as read:
                            with self.assertRaisesRegex(
                                ValueError, "^wheel_source_payload_mismatch$"
                            ):
                                package_check.validate_source_payload(raw, payload, package)
                            read.assert_not_called()

    def test_ordinary_data_resources_still_pass(self):
        for package in ("aethron", "aethron_edge"):
            with self.subTest(package=package):
                raw, payload = wheel_bytes(
                    package,
                    {
                        f"{package}-0.2.0.data/data/{package}/example.py": b"# example\n",
                        f"{package}-0.2.0.data/data/share/{package}/notes.txt": b"notes\n",
                        f"{package}-0.2.0.data/data/share/site-packages.txt": b"notes\n",
                    },
                )
                package_check.validate_source_payload(raw, payload, package)

    def test_real_installer_places_data_records_in_import_directory(self):
        # Install only inert fixtures in a disposable environment: this proves
        # the relocation without executing a startup hook or importing a package.
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
            relative = site.relative_to(environment).as_posix()
            raw, payload = wheel_bytes(
                "aethron",
                {
                    f"aethron-0.2.0.data/data/{relative}/aethron/module.py": b"VALUE = 2\n",
                    f"aethron-0.2.0.data/data/{relative}/fixture.pth": b"# inert fixture\n",
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
            self.assertEqual((site / "aethron/module.py").read_bytes(), b"VALUE = 2\n")
            self.assertEqual((site / "fixture.pth").read_bytes(), b"# inert fixture\n")
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload)
