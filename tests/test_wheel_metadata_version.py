"""Wheel metadata cannot report a version different from its install directory."""

import importlib.metadata
import io
import os
import subprocess
import tempfile
import unittest
import venv
import zipfile
from pathlib import Path

from test_wheel_metadata_name import metadata_wheel

from scripts import package_check


class WheelMetadataVersion(unittest.TestCase):
    def test_directory_versions_and_pep440_normalization(self):
        for directory_version, version, accepted in (
            ("0.2.0rc1", "0.2.0c1", True),
            ("0.2.0.post1", "0.2.0-1", True),
            ("0.2.0.dev1", "0.2.0dev1", True),
            ("0.2.0+local.1", "0.2.0+LOCAL-1", True),
            ("invalid", "0.2.0", False),
            ("", "0.2.0", False),
            ("0.2.0rc1", "0.2.0", False),
        ):
            with self.subTest(directory_version=directory_version, version=version):
                raw, payload = metadata_wheel(
                    "aethron", f"Metadata-Version: 2.1\nName: aethron\nVersion: {version}\n"
                )
                output = io.BytesIO()
                with (
                    zipfile.ZipFile(io.BytesIO(raw)) as source,
                    zipfile.ZipFile(output, "w") as wheel,
                ):
                    for member in source.infolist():
                        name = member.filename.replace(
                            "aethron-0.2.0.dist-info", f"aethron-{directory_version}.dist-info"
                        )
                        wheel.writestr(name, source.read(member))
                if accepted:
                    package_check.validate_source_payload(output.getvalue(), payload)
                else:
                    with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                        package_check.validate_source_payload(output.getvalue(), payload)

    def test_invalid_version_error_does_not_echo_metadata(self):
        for version in ("private-fixture-token", "9" * 5000):
            with self.subTest(length=len(version)):
                raw, payload = metadata_wheel("aethron", f"Name: aethron\nVersion: {version}\n")
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.validate_source_payload(raw, payload)

    def test_missing_ambiguous_invalid_and_mismatched_versions_reject(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for headers in (
                    "",
                    "Version: \n",
                    "Version: 9.0\n",
                    "Version: 0.2.0\nversion: 0.2.0\n",
                    "Version: 0.2.0\nVersion: 9.0\n",
                    "Version: not-a-version\n",
                    "Version: 0.2.0\x00\n",
                    "Version: 0.2.0\n continuation\n",
                    "Version: 0.2.0+different\n",
                    "Version: 0.2.0rc1\n",
                ):
                    with self.subTest(package=package, layout=layout, headers=headers):
                        raw, payload = metadata_wheel(
                            package, f"Metadata-Version: 2.1\nName: {package}\n" + headers, layout
                        )
                        with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                            package_check.validate_source_payload(raw, payload, package)

    def test_equivalent_versions_and_description_are_accepted(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for version in ("0.2.0", "0.2", "0.2.0.0", "v0.2.0", "00.02.00"):
                    with self.subTest(package=package, layout=layout, version=version):
                        raw, payload = metadata_wheel(
                            package,
                            f"Metadata-Version: 2.1\r\nName: {package}\r\nVersion: {version}\r\n"
                            "\r\nVersion: 9.0 is only description text.\r\n",
                            layout,
                            extras={f"{package}/examples/foreign.dist-info/METADATA": b"example"},
                        )
                        package_check.validate_source_payload(raw, payload, package)

    def test_offline_installer_reports_mismatched_version_with_unchanged_sources(self):
        # Inert fixture only: demonstrate metadata discovery, never run its code.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            raw, payload = metadata_wheel(
                "aethron", "Metadata-Version: 2.1\nName: aethron\nVersion: 9.0\n"
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
            result = subprocess.run(
                [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            site = Path(result.stdout.strip())
            distribution = importlib.metadata.PathDistribution(site / "aethron-0.2.0.dist-info")
            self.assertEqual(distribution.version, "9.0")
            self.assertEqual(package_check.snapshot_source_payload(site), payload)
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload)
