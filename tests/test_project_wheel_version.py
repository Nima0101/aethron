"""Self-consistent wheel versions must still match the source project."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import test_core_package_report as core_tests
import test_edge_package_input_evidence as edge_tests
from test_wheel_data_destinations import wheel_bytes

from scripts import package_check


class ProjectWheelVersion(unittest.TestCase):
    def test_declared_version_uses_toml_and_pep440_semantics(self):
        raw, payload = wheel_bytes("aethron", {})
        for declaration in ('"0.2"', "'0.2.0.0'", '"\\u0030.2.0"'):
            with self.subTest(declaration=declaration), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "pyproject.toml").write_text(
                    f'[project]\nversion = {declaration} # static\n[tool.fixture]\nversion = "9.0"\n'
                )
                package_check.validate_source_payload(
                    raw,
                    payload,
                    wheel_filename="aethron-0.2.0-py3-none-any.whl",
                    expected_project_version=package_check.project_version(root),
                )

    def test_unusable_project_versions_reject(self):
        for declaration in (
            "",
            "project = []",
            "[project]",
            "[project]\nversion = 2",
            "[project]\nversion = true",
            "[project]\nversion = []",
            '[project]\nversion = "invalid"',
            '[project]\nversion = ""',
            '[project]\nversion = "0.2.0"\nversion = "9.0"',
            '[project]\nversion = "0.2.0"\ndynamic = ["version"]',
            '[project]\nversion = "0.2.0"\ndynamic = "version"',
            '[project]\nversion = "unterminated',
        ):
            with self.subTest(declaration=declaration), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "pyproject.toml").write_text(declaration)
                with self.assertRaisesRegex(ValueError, "^invalid_project_version$"):
                    package_check.project_version(root)

    def substituted_version(self, package):
        original = package_check.wheel_paths

        def inventory(directory):
            for wheel in original(directory):
                if not wheel.name.startswith(package + "-"):
                    continue
                version = wheel.name.split("-")[1]
                buffer = io.BytesIO()
                with zipfile.ZipFile(wheel) as before, zipfile.ZipFile(buffer, "w") as after:
                    for member in before.infolist():
                        data = before.read(member)
                        if member.filename.endswith(("/METADATA", "/RECORD")):
                            data = data.replace(version.encode(), b"9.0")
                        after.writestr(member.filename.replace(version, "9.0"), data)
                wheel.unlink()
                wheel.with_name(wheel.name.replace("-" + version + "-", "-9.0-", 1)).write_bytes(
                    buffer.getvalue()
                )
            return original(directory)

        return patch.object(package_check, "wheel_paths", side_effect=inventory)

    def test_core_rejects_consistently_wrong_version_before_install(self):
        with core_tests.CorePackageReport().fixture() as (output, installed, calls):
            with self.substituted_version("aethron"):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.run()
            self.assertEqual(installed, [])
            self.assertEqual(output.getvalue(), "")
            self.assertFalse(any("venv" in args for args in calls))

    def test_edge_rejects_either_consistently_wrong_version_before_install(self):
        for package in ("aethron", "aethron_edge"):
            calls = []
            with self.subTest(package=package), self.substituted_version(package):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    edge_tests.PackageInputEvidence().probe(on_run=calls.append)
                self.assertFalse(any("venv" in args for args in calls))
