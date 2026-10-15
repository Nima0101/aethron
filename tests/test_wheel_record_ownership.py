"""A wheel's removal inventory may claim only files actually in that archive."""

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

from test_wheel_data_destinations import wheel_bytes
from wheel_fixtures import record_row

from scripts import package_check


def record_wheel(package, record, layout="", extras=None, complete=False):
    raw, payload = wheel_bytes(package, extras or {})
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(output, "w") as wheel:
        record_path = f"{package}-0.2.0.dist-info/RECORD"
        if complete:
            # Positive fixtures need a complete inventory while retaining the
            # exact declarations under test. Negative fixtures remain literal.
            seen = {row[0] for row in csv.reader(io.StringIO(record))}
            missing = io.StringIO(newline="")
            writer = csv.writer(missing)
            for member in source.infolist():
                name = (
                    layout + member.filename if member.filename == record_path else member.filename
                )
                if not member.is_dir() and name not in seen:
                    writer.writerow(
                        (name, "", "")
                        if member.filename == record_path
                        else record_row(name, source.read(member))
                    )
            record += missing.getvalue()
        for member in source.infolist():
            if member.filename == record_path:
                wheel.writestr(layout + member.filename, record)
            else:
                wheel.writestr(member, source.read(member))
    return output.getvalue(), payload


class WheelRecordOwnership(unittest.TestCase):
    def test_unowned_and_aliased_record_paths_reject(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for path in (
                    "foreign-fixture.txt",
                    "../../../foreign-fixture.txt",
                    "/foreign-fixture.txt",
                    "C:/foreign-fixture.txt",
                    f"./{package}/module.py",
                    f"{package}/../{package}/module.py",
                    f"{package}\\module.py",
                    f"{package}/MODULE.py",
                    f"{package}/module.py\x00",
                    f"{package}/",
                ):
                    with self.subTest(package=package, layout=layout, path=path):
                        raw, payload = record_wheel(package, path + ",,\n", layout)
                        with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                            package_check.validate_source_payload(raw, payload, package)

    def test_malformed_and_duplicate_record_rows_reject(self):
        for record in (
            b"\xff,,\n",
            b'"unclosed,,\n',
            b"aethron/module.py\n",
            b"aethron/module.py,,,\n",
            b"aethron/module.py,,\naethron/module.py,,\n",
            b"\n",
            b",,\n",
        ):
            with self.subTest(record=record):
                raw, payload = record_wheel("aethron", record)
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.validate_source_payload(raw, payload)

    def test_valid_archive_paths_and_nested_example_are_accepted(self):
        for package in ("aethron", "aethron_edge"):
            resource = f"{package}-0.2.0.data/data/share/caf\u00e9,notes.txt"
            nested = f"{package}/examples/foreign.dist-info/RECORD"
            record = io.StringIO(newline="")
            csv.writer(record).writerows(
                (
                    record_row(f"{package}/module.py", b"VALUE = 1\n"),
                    record_row(resource, b"data"),
                    record_row(nested, b"example,,\n"),
                )
            )
            raw, payload = record_wheel(
                package,
                record.getvalue(),
                extras={resource: b"data", nested: b"example,,\n"},
                complete=True,
            )
            package_check.validate_source_payload(raw, payload, package)

    def test_oversized_directory_and_ambiguous_records_reject_before_reads(self):
        record = "aethron-0.2.0.dist-info/RECORD"
        for extras in (
            {record + "/": b""},
            {"aethron-9.0.dist-info/RECORD": b""},
        ):
            raw, payload = record_wheel("aethron", b"", extras=extras)
            with patch.object(zipfile.ZipFile, "read", side_effect=AssertionError("read")):
                with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                    package_check.validate_source_payload(raw, payload)
        raw, payload = record_wheel("aethron", b"x" * 1048577)
        with patch.object(zipfile.ZipFile, "read", side_effect=AssertionError("read")):
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload)

    def test_offline_uninstall_inventory_claims_unrelated_file(self):
        # Everything is inert and disposable. No package code is executed.
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
            unrelated = site / "foreign-fixture.txt"
            unrelated.write_bytes(b"not owned by this wheel\n")
            raw, payload = record_wheel("aethron", b"foreign-fixture.txt,,\n")
            wheel = root / "aethron-0.2.0-py3-none-any.whl"
            wheel.write_bytes(raw)
            pip = [str(python), "-I", "-m", "pip", "--isolated", "--disable-pip-version-check"]
            subprocess.run(
                pip + ["install", "--no-index", "--no-deps", "--no-compile", str(wheel)],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(package_check.snapshot_source_payload(site), payload)
            self.assertEqual(unrelated.read_bytes(), b"not owned by this wheel\n")
            subprocess.run(
                pip + ["uninstall", "--yes", "aethron"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=60,
            )
            self.assertFalse(unrelated.exists())
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload)
