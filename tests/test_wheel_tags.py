"""Wheel compatibility declarations must agree before offline installation."""

import io
import unittest
import zipfile
from unittest.mock import patch

import test_core_package_report as core_tests
import test_edge_package_input_evidence as edge_tests
from test_wheel_data_destinations import wheel_bytes
from wheel_fixtures import refresh_record

from scripts import package_check


def replace_tags(raw, headers):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as before, zipfile.ZipFile(output, "w") as after:
        for member in before.infolist():
            data = before.read(member)
            if member.filename.count("/") == 1 and member.filename.endswith(".dist-info/WHEEL"):
                data = b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\n" + headers
            after.writestr(member, data)
    # Keep RECORD valid so integrity failures cannot mask tag discrepancies.
    return refresh_record(output.getvalue())


class WheelTags(unittest.TestCase):
    def substituted_tags(self, package):
        original = package_check.wheel_paths

        def inventory(directory):
            for wheel in original(directory):
                if wheel.name.startswith(package + "-"):
                    wheel.write_bytes(
                        replace_tags(wheel.read_bytes(), b"Tag: py3-none-any\nTag: py2-none-any\n")
                    )
            return original(directory)

        return patch.object(package_check, "wheel_paths", side_effect=inventory)

    def test_core_rejects_conflicting_tags_before_install(self):
        with core_tests.CorePackageReport().fixture(real_install=True) as (
            output,
            installed,
            calls,
        ):
            with self.substituted_tags("aethron"):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.run()
            self.assertEqual(installed, [])
            self.assertEqual(output.getvalue(), "")
            self.assertFalse(any("venv" in args for args in calls))

    def test_edge_rejects_either_conflicting_tag_before_install(self):
        for package in ("aethron", "aethron_edge"):
            calls = []
            with self.subTest(package=package), self.substituted_tags(package):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    edge_tests.PackageInputEvidence().probe(on_run=calls.append)
                self.assertFalse(any("venv" in args for args in calls))

    def test_missing_malformed_duplicate_and_conflicting_tags_reject(self):
        for package in ("aethron", "aethron_edge"):
            raw, payload = wheel_bytes(package, {})
            for headers in (
                b"",
                b"Tag: \n",
                b"Tag: invalid\n",
                b"Tag: py3-none-any-extra\n",
                b"Tag: py2-none-any\n",
                b"Tag: py3-abi3-any\n",
                b"Tag: py3-none-win_amd64\n",
                b"Tag: py3-none-any\nTag: py3-none-any\n",
                b"Tag: py3-none-any\nTag: py2-none-any\n",
                b"Tag: py3-none-any\nmalformed header\n",
                b"Tag: \xff\n",
            ):
                with self.subTest(package=package, headers=headers):
                    with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                        package_check.validate_source_payload(
                            replace_tags(raw, headers),
                            payload,
                            package,
                            wheel_filename=f"{package}-0.2.0-py3-none-any.whl",
                        )

    def test_compressed_filename_tags_match_expanded_metadata_in_any_order(self):
        for package in ("aethron", "aethron_edge"):
            raw, payload = wheel_bytes(package, {})
            for headers in (
                b"Tag: py3-none-any\nTag: py2-none-any\n",
                b"Tag: py2-none-any\nTag: py3-none-any\n",
            ):
                with self.subTest(package=package, headers=headers):
                    package_check.validate_source_payload(
                        replace_tags(raw, headers),
                        payload,
                        package,
                        wheel_filename=f"{package}-0.2.0-1-py2.py3-none-any.whl",
                    )

    def test_spread_metadata_is_checked_and_nested_examples_are_resources(self):
        for package in ("aethron", "aethron_edge"):
            raw, payload = wheel_bytes(
                package, {f"{package}/examples/demo.dist-info/WHEEL": b"example"}
            )
            for layout in ("purelib", "platlib"):
                for headers, accepted in (
                    (b"Tag: py3-none-any\n", True),
                    (b"Tag: py2-none-any\n", False),
                ):
                    buffer = io.BytesIO()
                    with zipfile.ZipFile(io.BytesIO(replace_tags(raw, headers))) as before:
                        with zipfile.ZipFile(buffer, "w") as after:
                            for member in before.infolist():
                                # Omit optional inventory in this parser-only
                                # fixture to isolate spread destination handling.
                                if member.filename.endswith(".dist-info/RECORD"):
                                    continue
                                name = member.filename
                                if name.startswith(package + "-0.2.0.dist-info/"):
                                    name = f"{package}-0.2.0.data/{layout}/" + name
                                after.writestr(name, before.read(member))
                    with self.subTest(package=package, layout=layout, accepted=accepted):
                        args = (buffer.getvalue(), payload, package)
                        kwargs = {"wheel_filename": f"{package}-0.2.0-py3-none-any.whl"}
                        if accepted:
                            package_check.validate_source_payload(*args, **kwargs)
                        else:
                            with self.assertRaisesRegex(
                                ValueError, "^wheel_source_payload_mismatch$"
                            ):
                                package_check.validate_source_payload(*args, **kwargs)

    def test_oversized_metadata_rejects_before_reads(self):
        raw, payload = wheel_bytes("aethron", {})
        raw = replace_tags(raw, b"Tag: py3-none-any\nGenerator: " + b"x" * 65536)
        with patch.object(zipfile.ZipFile, "read", side_effect=AssertionError("unexpected read")):
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(
                    raw, payload, wheel_filename="aethron-0.2.0-py3-none-any.whl"
                )


if __name__ == "__main__":
    unittest.main()
