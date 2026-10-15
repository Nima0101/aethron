"""Static source dependency declarations must survive wheel construction."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import test_core_package_report as core_tests
import test_edge_package_input_evidence as edge_tests
import test_wheel_python_requirement as python_requirement_tests
from wheel_fixtures import refresh_record

from scripts import package_check


class WheelDependencies(unittest.TestCase):
    def test_static_source_contract_includes_empty_extras_and_conditional_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text(
                '[project]\ndependencies = ["base[Fast_Mode]>=2,<3"]\n'
                "[project.optional-dependencies]\nEmpty = []\n"
                "Test_Mode = [\"opt==1; os_name == 'nt' or python_version < '3'\"]\n"
            )
            expected = package_check.dependency_contract(
                [
                    "Base[fast-mode] <3, >=2.0",
                    'opt==1.0; (os_name == "nt" or python_version < "3") and extra == "test-mode"',
                ],
                ["empty", "test-mode"],
            )
            self.assertEqual(package_check.project_dependencies(root), expected)

    def test_invalid_or_dynamic_source_dependencies_reject(self):
        for declaration in (
            "",
            "project = []",
            '[project]\ndependencies = "dep"',
            "[project]\ndependencies = [1]",
            '[project]\ndependencies = ["bad ???"]',
            '[project]\ndynamic = ["dependencies"]',
            '[project]\ndynamic = ["optional-dependencies"]',
            '[project]\ndynamic = "dependencies"',
            "[project]\noptional-dependencies = []",
            '[project.optional-dependencies]\nvision = "dep"',
            "[project.optional-dependencies]\nvision = [false]",
            '[project.optional-dependencies]\nvision = ["bad ???"]',
            '[project.optional-dependencies]\n"bad?" = []',
            "[project.optional-dependencies]\nFoo_Bar = []\nfoo-bar = []",
        ):
            with self.subTest(declaration=declaration), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "pyproject.toml").write_text(declaration)
                with self.assertRaisesRegex(ValueError, "^invalid_project_dependencies$"):
                    package_check.project_dependencies(root)

    def test_absent_static_dependencies_mean_empty_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text("[project]\n")
            self.assertEqual(
                package_check.project_dependencies(root), package_check.dependency_contract([], [])
            )

    def test_metadata_parity_including_markers_urls_and_extra_inventory(self):
        expected = package_check.dependency_contract(
            [
                "base_pkg[fast-mode]>=2,<3",
                "opt==1; extra == 'feature'",
                "remote @ https://example.org/a.whl",
            ],
            ["feature", "empty"],
        )
        valid = (
            "Requires-Dist: remote @ https://example.org/a.whl\n"
            "Requires-Dist: Base-Pkg[fast_mode]<3,>=2.0\n"
            'Requires-Dist: opt==1.0; extra == "feature"\n'
            "Provides-Extra: empty\nProvides-Extra: Feature\n"
        )
        cases = (
            None,
            "",
            valid.replace("Base-Pkg[fast_mode]<3,>=2.0", "Base-Pkg>=1"),
            valid.replace('extra == "feature"', 'python_version < "2"'),
            valid.replace("Provides-Extra: empty\n", ""),
            valid + "Provides-Extra: empty\n",
            valid + "Provides-Extra: unknown\n",
            valid + "Requires-Dist: opt==1.0; extra == 'feature'\n",
            valid + "Requires-Dist: unexpected\n",
            valid + "Requires-Dist: invalid ???\n",
            valid.replace("https://example.org/a.whl", "https://example.org/b.whl"),
        )
        for package in ("aethron", "aethron_edge"):
            for layout in ("root", "purelib", "platlib"):
                fixture = python_requirement_tests.WheelPythonRequirement()
                raw, payload = fixture.metadata_wheel(package, valid, layout)
                package_check.validate_source_payload(
                    raw, payload, package, expected_dependencies=expected
                )
                for headers in cases:
                    with self.subTest(package=package, layout=layout, headers=headers):
                        raw, payload = fixture.metadata_wheel(package, headers, layout)
                        with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                            package_check.validate_source_payload(
                                raw, payload, package, expected_dependencies=expected
                            )

    def substituted_dependencies(self, package, headers):
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
                                    if not line.startswith(("Requires-Dist:", "Provides-Extra:"))
                                ).encode()
                                + headers.encode()
                            )
                        after.writestr(member, data)
                wheel.write_bytes(refresh_record(buffer.getvalue()))
            return original(directory)

        return patch.object(package_check, "wheel_paths", side_effect=inventory)

    def test_core_rejects_changed_dependencies_before_install(self):
        # The inactive marker passes a real offline pip check on this host.
        with core_tests.CorePackageReport().fixture(real_install=True) as (
            output,
            installed,
            calls,
        ):
            with self.substituted_dependencies(
                "aethron", "Requires-Dist: undeclared-probe; python_version < '2'\n"
            ):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.run()
            self.assertEqual(installed, [])
            self.assertEqual(output.getvalue(), "")
            self.assertFalse(any("venv" in args for args in calls))

    def test_edge_rejects_either_changed_dependency_before_install(self):
        for package in ("aethron", "aethron_edge"):
            calls = []
            with self.subTest(package=package):
                with self.substituted_dependencies(package, "Requires-Dist: undeclared-probe\n"):
                    with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                        edge_tests.PackageInputEvidence().probe(on_run=calls.append)
                self.assertFalse(any("venv" in args for args in calls))

    def test_core_rejects_omitted_dependency_before_install(self):
        with core_tests.CorePackageReport().fixture(
            requirements="Requires-Dist: aethron==0.2.0\n"
        ) as (output, installed, calls):
            with self.substituted_dependencies("aethron", ""):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.run()
            self.assertEqual(installed, [])
            self.assertEqual(output.getvalue(), "")
            self.assertFalse(any("venv" in args for args in calls))

    def test_edge_snapshots_both_dependency_contracts_before_build(self):
        original = package_check.project_dependencies
        snapshots = []

        def snapshot(root):
            result = original(root)
            snapshots.append(root)
            return result

        def on_run(args):
            if args[1:3] == ["-m", "build"]:
                self.assertEqual(len(snapshots), 2)
                # Mutation after capture must not redefine the expected contract.
                for root in snapshots:
                    (root / "pyproject.toml").write_text(
                        '[project]\ndependencies = ["changed-after-snapshot"]\n'
                    )

        with patch.object(package_check, "project_dependencies", side_effect=snapshot):
            # The existing final input-hash check also detects this source edit.
            with self.assertRaisesRegex(ValueError, "^package_input_changed$"):
                edge_tests.PackageInputEvidence().probe(on_run=on_run)
