"""Release filenames must describe the version an offline install discovers."""

import importlib.metadata
import os
import subprocess
import tempfile
import unittest
import venv
from pathlib import Path
from unittest.mock import patch

import test_core_package_report as core_tests
import test_edge_package_input_evidence as edge_tests
from test_wheel_data_destinations import wheel_bytes

from scripts import package_check


class WheelFilenameVersion(unittest.TestCase):
    def renamed_inventory(self, package):
        original = package_check.wheel_paths

        def inventory(directory):
            for wheel in original(directory):
                if wheel.name.startswith(package + "-"):
                    version = wheel.name.split("-")[1]
                    wheel.rename(
                        wheel.with_name(wheel.name.replace("-" + version + "-", "-9.0-", 1))
                    )
            return original(directory)

        return patch.object(package_check, "wheel_paths", side_effect=inventory)

    def test_core_rejects_renamed_version_before_install(self):
        with core_tests.CorePackageReport().fixture() as (output, installed, calls):
            with self.renamed_inventory("aethron"):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.run()
            self.assertEqual(installed, [])
            self.assertEqual(output.getvalue(), "")
            self.assertFalse(any("venv" in args for args in calls))

    def test_edge_rejects_either_renamed_version_before_install(self):
        for package in ("aethron", "aethron_edge"):
            calls = []
            with self.subTest(package=package), self.renamed_inventory(package):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    edge_tests.PackageInputEvidence().probe(on_run=calls.append)
                self.assertFalse(any("venv" in args for args in calls))

    def test_offline_installer_can_discover_a_different_version_than_filename(self):
        # Only inert synthetic bytes are installed; no product code is executed.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            raw, payload = wheel_bytes("aethron", {})
            wheel = root / "aethron-9.0-py3-none-any.whl"
            wheel.write_bytes(raw)
            result = subprocess.run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--no-deps",
                    "--no-compile",
                    str(wheel),
                ],
                cwd=root,
                env=package_check.packaging_environment(),
                check=True,
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0)
            result = subprocess.run(
                [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            site = Path(result.stdout.strip())
            installed = importlib.metadata.PathDistribution(site / "aethron-0.2.0.dist-info")
            self.assertEqual(installed.version, "0.2.0")
            self.assertEqual(package_check.snapshot_source_payload(site), payload)
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload, wheel_filename=wheel.name)

    def test_filename_versions_use_pep440_equivalence_and_optional_build_tag(self):
        for package in ("aethron", "aethron_edge"):
            raw, payload = wheel_bytes(package, {})
            for version in ("0.2", "0.2.0", "0.2.0.0"):
                for build in ("", "-1", "-12build"):
                    with self.subTest(package=package, version=version, build=build):
                        package_check.validate_source_payload(
                            raw,
                            payload,
                            package,
                            wheel_filename=f"{package}-{version}{build}-py3-none-any.whl",
                        )

    def test_invalid_foreign_and_different_filename_versions_reject(self):
        raw, payload = wheel_bytes("aethron", {})
        for filename in (
            "invalid.whl",
            "foreign-0.2.0-py3-none-any.whl",
            "aethron-0.2.0rc1-py3-none-any.whl",
            "aethron-0.2.0+local-py3-none-any.whl",
            "aethron-0.2.0.post1-py3-none-any.whl",
            "aethron-9.0-py3-none-any.whl",
        ):
            with self.subTest(filename=filename):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.validate_source_payload(raw, payload, wheel_filename=filename)
