"""Archive RECORD hashes are mandatory even though installed RECORD permits blanks."""

import csv
import io
import unittest
import zipfile
from unittest.mock import patch

import test_core_package_report as core_tests
import test_edge_package_input_evidence as edge_tests
from test_wheel_record_coverage import inventory_wheel

from scripts import package_check


def omit_hash(raw, target):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as before, zipfile.ZipFile(output, "w") as after:
        for member in before.infolist():
            data = before.read(member)
            if member.filename.endswith(".dist-info/RECORD"):
                rows = list(csv.reader(io.StringIO(data.decode())))
                for row in rows:
                    if row[0] == target:
                        row[1] = ""
                record = io.StringIO(newline="")
                csv.writer(record).writerows(rows)
                data = record.getvalue().encode()
            after.writestr(member, data)
    return output.getvalue()


class WheelRequiredHashes(unittest.TestCase):
    def test_source_metadata_and_resource_hashes_are_required(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                raw, payload = inventory_wheel(package, layout, signatures=True)
                for target in (
                    f"{package}/module.py",
                    layout + f"{package}-0.2.0.dist-info/METADATA",
                    layout + f"{package}-0.2.0.dist-info/WHEEL",
                    f"{package}/resources/caf\u00e9,notes.txt",
                    f"{package}/examples/RECORD.jws",
                    f"{package}/examples/RECORD.p7s",
                    f"{package}-0.2.0.data/data/share/license.txt",
                ):
                    with self.subTest(package=package, layout=layout, target=target):
                        with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                            package_check.validate_source_payload(
                                omit_hash(raw, target), payload, package
                            )

    def missing_hash(self, package):
        original = package_check.wheel_paths

        def inventory(directory):
            for wheel in original(directory):
                if wheel.name.startswith(package + "-"):
                    wheel.write_bytes(omit_hash(wheel.read_bytes(), package + "/__init__.py"))
            return original(directory)

        return patch.object(package_check, "wheel_paths", side_effect=inventory)

    def test_core_missing_hash_rejects_before_real_install(self):
        with core_tests.CorePackageReport().fixture(real_install=True) as (
            output,
            installed,
            calls,
        ):
            with self.missing_hash("aethron"):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.run()
            self.assertEqual(installed, [])
            self.assertEqual(output.getvalue(), "")
            self.assertFalse(any("venv" in args for args in calls))

    def test_edge_missing_hash_rejects_before_install(self):
        for package in ("aethron", "aethron_edge"):
            calls = []
            with self.subTest(package=package), self.missing_hash(package):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    edge_tests.PackageInputEvidence().probe(on_run=calls.append)
                self.assertFalse(any("venv" in args for args in calls))
