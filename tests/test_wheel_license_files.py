"""Declared PEP 639 license files must be included in wheel installations."""

import csv
import io
import unittest
import zipfile
from unittest.mock import patch

import test_core_package_report as core_tests
import test_edge_package_input_evidence as edge_tests
from test_wheel_data_destinations import wheel_bytes

from scripts import package_check


def declare_license(raw, declaration="LICENSE", version="2.4", metadata_layout=""):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as before, zipfile.ZipFile(output, "w") as after:
        record_name = None
        for member in before.infolist():
            if member.filename.endswith("/RECORD"):
                record_name = member.filename
                continue
            data = before.read(member)
            name = member.filename
            if name.endswith("/METADATA"):
                name = metadata_layout + name
                data = data.replace(
                    b"Metadata-Version: 2.1", f"Metadata-Version: {version}".encode()
                )
                data += f"License-File: {declaration}\n".encode()
            after.writestr(name, data)
        if record_name is not None:
            record = io.StringIO(newline="")
            csv.writer(record).writerows(
                (item.filename, "", "") for item in after.infolist() if not item.is_dir()
            )
            csv.writer(record).writerow((record_name, "", ""))
            after.writestr(record_name, record.getvalue())
    return output.getvalue()


class WheelLicenseFiles(unittest.TestCase):
    def test_declared_file_must_exist_at_exact_license_destination(self):
        for package in ("aethron", "aethron_edge"):
            metadata = f"{package}-0.2.0.dist-info/"
            for misplaced in (
                None,
                "LICENSE",
                metadata + "LICENSE",
                metadata + "licenses/LICENSE/",
                metadata + "licenses/license",
            ):
                with self.subTest(package=package, misplaced=misplaced):
                    extras = {} if misplaced is None else {misplaced: b"fixture notice"}
                    raw, payload = wheel_bytes(package, extras)
                    with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                        package_check.validate_source_payload(
                            declare_license(raw), payload, package
                        )

    def test_relative_paths_and_spread_license_files_pass(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for filename in ("LICENSE", "vendor/Notice caf\u00e9.txt"):
                    with self.subTest(package=package, layout=layout, filename=filename):
                        raw, payload = wheel_bytes(
                            package,
                            {
                                layout
                                + f"{package}-0.2.0.dist-info/licenses/"
                                + filename: b"fixture notice"
                            },
                        )
                        package_check.validate_source_payload(
                            declare_license(raw, filename, metadata_layout=layout), payload, package
                        )

    def test_non_relative_and_ambiguous_paths_reject(self):
        for declaration in (
            "",
            "/LICENSE",
            "../LICENSE",
            "vendor/../LICENSE",
            "./LICENSE",
            "vendor//LICENSE",
            "vendor\\LICENSE",
            "C:/LICENSE",
            "LICENSE\nLicense-File: LICENSE",
        ):
            with self.subTest(declaration=declaration):
                raw, payload = wheel_bytes(
                    "aethron", {"aethron-0.2.0.dist-info/licenses/LICENSE": b"fixture notice"}
                )
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.validate_source_payload(
                        declare_license(raw, declaration), payload
                    )

    def test_legacy_metadata_is_not_reinterpreted_as_pep639(self):
        raw, payload = wheel_bytes(
            "aethron", {"aethron-0.2.0.dist-info/LICENSE": b"fixture notice"}
        )
        package_check.validate_source_payload(declare_license(raw, version="2.1"), payload)

    def test_multiple_declared_files_must_all_exist(self):
        for complete in (False, True):
            extras = {"aethron-0.2.0.dist-info/licenses/LICENSE": b"fixture notice"}
            if complete:
                extras["aethron-0.2.0.dist-info/licenses/vendor/NOTICE"] = b"vendor notice"
            raw, payload = wheel_bytes("aethron", extras)
            raw = declare_license(raw, "LICENSE\nLicense-File: vendor/NOTICE")
            if complete:
                package_check.validate_source_payload(raw, payload)
            else:
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.validate_source_payload(raw, payload)

    def test_ambiguous_or_invalid_metadata_version_cannot_waive_inclusion(self):
        raw, payload = wheel_bytes("aethron", {})
        for version in ("", "invalid", "2.4\nMetadata-Version: 2.1", "9" * 5000 + ".0"):
            with self.subTest(version_length=len(version)):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.validate_source_payload(
                        declare_license(raw, version=version), payload
                    )

    def missing_license(self, package):
        original = package_check.wheel_paths

        def inventory(directory):
            for wheel in original(directory):
                if wheel.name.startswith(package + "-"):
                    wheel.write_bytes(declare_license(wheel.read_bytes()))
            return original(directory)

        return patch.object(package_check, "wheel_paths", side_effect=inventory)

    def test_core_missing_license_rejects_before_real_install(self):
        with core_tests.CorePackageReport().fixture(real_install=True) as (
            output,
            installed,
            calls,
        ):
            with self.missing_license("aethron"):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.run()
            self.assertEqual(installed, [])
            self.assertEqual(output.getvalue(), "")
            self.assertFalse(any("venv" in args for args in calls))

    def test_edge_missing_license_rejects_before_install(self):
        for package in ("aethron", "aethron_edge"):
            calls = []
            with self.subTest(package=package), self.missing_license(package):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    edge_tests.PackageInputEvidence().probe(on_run=calls.append)
                self.assertFalse(any("venv" in args for args in calls))
