"""Built license declarations must match their static source projects."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import test_core_package_report as core_tests
import test_edge_package_input_evidence as edge_tests
import test_wheel_python_requirement as python_tests

from scripts import package_check


class WheelLicense(unittest.TestCase):
    def substituted_license(self, package):
        original = package_check.wheel_paths

        def inventory(directory):
            for wheel in original(directory):
                if not wheel.name.startswith(package + "-"):
                    continue
                output = io.BytesIO()
                with zipfile.ZipFile(wheel) as before, zipfile.ZipFile(output, "w") as after:
                    for member in before.infolist():
                        data = before.read(member)
                        if member.filename.endswith("/METADATA"):
                            lines = data.decode().splitlines(keepends=True)
                            data = (
                                "".join(
                                    line
                                    for line in lines
                                    if not line.startswith("License-Expression:")
                                )
                                + "License-Expression: MIT\n"
                            ).encode()
                        after.writestr(member, data)
                wheel.write_bytes(output.getvalue())
            return original(directory)

        return patch.object(package_check, "wheel_paths", side_effect=inventory)

    def test_core_rejects_changed_license_before_install(self):
        with core_tests.CorePackageReport().fixture(real_install=True) as (
            output,
            installed,
            calls,
        ):
            with self.substituted_license("aethron"):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.run()
            self.assertEqual(installed, [])
            self.assertEqual(output.getvalue(), "")
            self.assertFalse(any("venv" in args for args in calls))

    def test_edge_rejects_either_changed_license_before_install(self):
        for package in ("aethron", "aethron_edge"):
            calls = []
            with self.subTest(package=package), self.substituted_license(package):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    edge_tests.PackageInputEvidence().probe(on_run=calls.append)
                self.assertFalse(any("venv" in args for args in calls))

    def test_static_source_license_is_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text('[project]\nlicense = "gpl-3.0-only"\n')
            self.assertEqual(package_check.project_license(root), "GPL-3.0-only")

    def test_build_cannot_redefine_source_license_to_match_changed_wheel(self):
        for package in ("aethron", "aethron_edge"):
            calls = []

            def change_project(args, calls=calls, package=package):
                calls.append(args)
                if args[1:4] == ["-m", "build", "--no-isolation"]:
                    project = Path(args[-1])
                    if (project.name == "edge") == (package == "aethron_edge"):
                        manifest = project / "pyproject.toml"
                        manifest.write_text(manifest.read_text().replace("GPL-3.0-only", "MIT"))

            with self.subTest(package=package), self.substituted_license(package):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    edge_tests.PackageInputEvidence().probe(on_run=change_project)
                self.assertFalse(any("venv" in args for args in calls))

    def test_missing_invalid_or_dynamic_source_license_rejects(self):
        for declaration in (
            "",
            "project = []",
            "[project]",
            "[project]\nlicense = false",
            '[project]\nlicense = {text = "GPL-3.0-only"}',
            '[project]\nlicense = "unknown-license"',
            '[project]\nlicense = ""',
            '[project]\nlicense = "GPL-3.0-only"\ndynamic = ["license"]',
            '[project]\nlicense = "GPL-3.0-only"\ndynamic = "license"',
        ):
            with self.subTest(declaration=declaration), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "pyproject.toml").write_text(declaration)
                with self.assertRaisesRegex(ValueError, "^invalid_project_license$"):
                    package_check.project_license(root)

    def test_missing_duplicate_invalid_or_changed_wheel_license_rejects(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("root", "purelib", "platlib"):
                for headers in (
                    None,
                    "",
                    "License-Expression: \n",
                    "License-Expression: MIT\n",
                    "License-Expression: GPL-3.0-or-later\n",
                    "License-Expression: GPL-3.0-only OR MIT\n",
                    "License-Expression: unknown-license\n",
                    "License-Expression: GPL-3.0-only\nLicense-Expression: GPL-3.0-only\n",
                ):
                    with self.subTest(package=package, layout=layout, headers=headers):
                        raw, payload = python_tests.WheelPythonRequirement().metadata_wheel(
                            package, headers, layout
                        )
                        with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                            package_check.validate_source_payload(
                                raw, payload, package, expected_license="GPL-3.0-only"
                            )

    def test_normalized_wheel_license_passes_without_changing_expression(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("root", "purelib", "platlib"):
                raw, payload = python_tests.WheelPythonRequirement().metadata_wheel(
                    package, "License-Expression: gpl-3.0-only\n", layout
                )
                with self.subTest(package=package, layout=layout):
                    package_check.validate_source_payload(
                        raw, payload, package, expected_license="GPL-3.0-only"
                    )
