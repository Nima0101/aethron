"""A wheel's Python support declaration must match its static source project."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import test_core_package_report as core_tests
import test_edge_package_input_evidence as edge_tests
from packaging.specifiers import SpecifierSet
from test_wheel_data_destinations import wheel_bytes

from scripts import package_check


class WheelPythonRequirement(unittest.TestCase):
    def test_project_requirement_uses_static_toml_declaration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text(
                '[project]\nrequires-python = " >=3.9, <4 "\n'
                '[tool.fixture]\nrequires-python = "<3"\n'
            )
            self.assertEqual(
                package_check.project_requires_python(root), SpecifierSet("<4,>=3.9.0")
            )

    def test_invalid_project_requirements_reject(self):
        for declaration in (
            "",
            "project = []",
            "[project]",
            "[project]\nrequires-python = 3",
            "[project]\nrequires-python = false",
            "[project]\nrequires-python = []",
            '[project]\nrequires-python = "invalid"',
            '[project]\nrequires-python = ">=3.9"\ndynamic = ["requires-python"]',
            '[project]\nrequires-python = ">=3.9"\ndynamic = "requires-python"',
            '[project]\nrequires-python = ">=3.9"\nrequires-python = "<3"',
        ):
            with self.subTest(declaration=declaration), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "pyproject.toml").write_text(declaration)
                with self.assertRaisesRegex(ValueError, "^invalid_project_requires_python$"):
                    package_check.project_requires_python(root)

    def metadata_wheel(self, package, header, layout="root"):
        raw, payload = wheel_bytes(package, {})
        result = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as before, zipfile.ZipFile(result, "w") as after:
            for member in before.infolist():
                # These focused metadata fixtures omit RECORD. Inventory/hash
                # checks have separate tests; keep this rejection independent.
                if member.filename.endswith("/RECORD"):
                    continue
                name = member.filename
                data = before.read(member)
                if name.endswith("/METADATA"):
                    if header is None:
                        continue
                    data += header.encode()
                    if layout != "root":
                        name = f"{package}-0.2.0.data/{layout}/" + name
                after.writestr(name, data)
        return result.getvalue(), payload

    def test_normalized_specifiers_and_spread_metadata_pass(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("root", "purelib", "platlib"):
                for expected, supplied in (
                    (">=3.9,<4", "<4, >=3.9.0"),
                    (">=3.11", ">=3.11.0"),
                    ("", ""),
                ):
                    with self.subTest(package=package, layout=layout, supplied=supplied):
                        raw, payload = self.metadata_wheel(
                            package, f"Requires-Python: {supplied}\n", layout
                        )
                        package_check.validate_source_payload(
                            raw, payload, package, expected_requires_python=SpecifierSet(expected)
                        )

    def test_missing_or_mismatched_metadata_rejects_in_each_layout(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("root", "purelib", "platlib"):
                for header in (
                    None,
                    "",
                    "Requires-Python: \n",
                    "Requires-Python: >=3.8\n",
                    "Requires-Python: >=3.10\n",
                    "Requires-Python: >=3.9\nRequires-Python: >=3.9\n",
                    "Requires-Python: >=3.9; os_name == 'posix'\n",
                ):
                    with self.subTest(package=package, layout=layout, header=header):
                        raw, payload = self.metadata_wheel(package, header, layout)
                        with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                            package_check.validate_source_payload(
                                raw,
                                payload,
                                package,
                                expected_requires_python=SpecifierSet(">=3.9"),
                            )

    def substituted_requirement(self, package, headers):
        original = package_check.wheel_paths

        def inventory(directory):
            for wheel in original(directory):
                if not wheel.name.startswith(package + "-"):
                    continue
                buffer = io.BytesIO()
                with zipfile.ZipFile(wheel) as before, zipfile.ZipFile(buffer, "w") as after:
                    for member in before.infolist():
                        data = before.read(member)
                        if member.filename.endswith("/METADATA"):
                            lines = data.decode().splitlines(keepends=True)
                            data = (
                                "".join(
                                    line
                                    for line in lines
                                    if not line.startswith("Requires-Python:")
                                ).encode()
                                + headers.encode()
                            )
                        after.writestr(member, data)
                wheel.write_bytes(buffer.getvalue())
            return original(directory)

        return patch.object(package_check, "wheel_paths", side_effect=inventory)

    def test_core_rejects_changed_python_requirement_before_install(self):
        for headers in (
            "Requires-Python: >=3.8\n",
            "Requires-Python: >=3.10\n",
            "",
            "Requires-Python: >=3.9\nRequires-Python: >=3.9\n",
            "Requires-Python: invalid\n",
        ):
            with self.subTest(headers=headers):
                with core_tests.CorePackageReport().fixture() as (output, installed, calls):
                    with self.substituted_requirement("aethron", headers):
                        with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                            package_check.run()
                    self.assertEqual(installed, [])
                    self.assertEqual(output.getvalue(), "")
                    self.assertFalse(any("venv" in args for args in calls))

    def test_edge_rejects_either_changed_python_requirement_before_install(self):
        for package in ("aethron", "aethron_edge"):
            calls = []
            with self.subTest(package=package):
                with self.substituted_requirement(package, "Requires-Python: >=3.8\n"):
                    with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                        edge_tests.PackageInputEvidence().probe(on_run=calls.append)
                self.assertFalse(any("venv" in args for args in calls))
