"""Installed distribution identity must agree with the verified package owner."""

import csv
import importlib.metadata
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

from scripts import package_check


def metadata_wheel(package, contents, layout="", extras=None):
    raw, payload = wheel_bytes(package, extras or {})
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(output, "w") as wheel:
        for member in source.infolist():
            if member.filename.endswith(".dist-info/METADATA"):
                wheel.writestr(layout + member.filename, contents)
            elif member.filename == f"{package}-0.2.0.dist-info/RECORD":
                record = io.StringIO(newline="")
                rows = csv.reader(io.StringIO(source.read(member).decode()))
                csv.writer(record).writerows(
                    (layout + name if name.endswith(".dist-info/METADATA") else name, digest, size)
                    for name, digest, size in rows
                )
                wheel.writestr(member, record.getvalue())
            else:
                wheel.writestr(member, source.read(member))
    return output.getvalue(), payload


class WheelMetadataName(unittest.TestCase):
    def test_malformed_or_foreign_identity_rejects(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for headers in (
                    "Name: foreign-fixture\n",
                    "",
                    f"Name: {package}\nname: {package}\n",
                    f"Name: {package}\nName: foreign-fixture\n",
                    f"Name: {package}\n foreign-fixture\n",
                    f"Name: {package}\x00\n",
                    f"Name: {package} \n",
                    f"Name: {package}-\n",
                    f"Name: {package}\nmalformed header\n",
                    "Name: \uff41ethron\n",
                    "Name: =?utf-8?q?aethron?=\n",
                ):
                    with self.subTest(package=package, layout=layout, headers=headers):
                        contents = "Metadata-Version: 2.1\n" + headers + "Version: 0.2.0\n"
                        raw, payload = metadata_wheel(package, contents, layout)
                        with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                            package_check.validate_source_payload(raw, payload, package)

    def test_normalized_names_and_description_are_accepted(self):
        for package, names in (
            ("aethron", ("aethron", "AETHRON")),
            ("aethron_edge", ("aethron-edge", "AETHRON_EDGE", "aethron.edge", "aethron-._edge")),
        ):
            for name in names:
                for newline in ("\n", "\r\n"):
                    with self.subTest(package=package, name=name, newline=newline):
                        contents = newline.join(
                            (
                                "Metadata-Version: 2.4",
                                "Name: " + name,
                                "Version: 0.2.0",
                                "Summary: caf\u00e9",
                                "",
                                "Name: foreign-fixture is only description text.",
                                "",
                            )
                        )
                        raw, payload = metadata_wheel(package, contents)
                        package_check.validate_source_payload(raw, payload, package)

    def test_invalid_utf8_rejects_without_echoing_bytes(self):
        raw, payload = metadata_wheel("aethron", b"Name: aethron\n\nprivate-fixture-\xff")
        with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$") as failure:
            package_check.validate_source_payload(raw, payload)
        self.assertTrue(failure.exception.__suppress_context__)

    def test_oversized_directory_and_multiple_metadata_reject_before_reads(self):
        metadata = "aethron-0.2.0.dist-info/METADATA"
        for extras in (
            {"aethron-9.0.dist-info/METADATA": b"Name: aethron\n"},
            {"aethron-0.2.0.data/purelib/aethron-9.0.dist-info/METADATA": b"Name: aethron\n"},
        ):
            raw, payload = wheel_bytes("aethron", extras)
            with self.subTest(extras=tuple(extras)):
                self.assert_rejected_before_reads(raw, payload)
        for name, contents in ((metadata, b"x" * (1048576 + 1)), (metadata + "/", b"")):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as wheel:
                wheel.writestr("aethron/module.py", b"VALUE = 1\n")
                wheel.writestr(name, contents)
            with self.subTest(name=name, size=len(contents)):
                self.assert_rejected_before_reads(
                    output.getvalue(), {"aethron/module.py": b"VALUE = 1\n"}
                )

    def assert_rejected_before_reads(self, raw, payload):
        with patch.object(zipfile.ZipFile, "read", side_effect=AssertionError("payload read")):
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload)

    def test_size_boundary_and_nested_metadata_examples_pass(self):
        prefix = b"Metadata-Version: 2.1\nName: aethron\nVersion: 0.2.0\n\n"
        raw, payload = metadata_wheel(
            "aethron",
            prefix + b"x" * (1048576 - len(prefix)),
            extras={"aethron/examples/foreign.dist-info/METADATA": b"not metadata\n"},
        )
        package_check.validate_source_payload(raw, payload)

    def test_installer_preserves_false_name_while_sources_still_match(self):
        # Inert synthetic source only, installed offline into a disposable venv.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            raw, payload = wheel_bytes(
                "aethron_edge",
                {
                    "aethron_edge-0.2.0.data/purelib/aethron_edge-9.0.dist-info/METADATA": "Metadata-Version: 2.1\nName: foreign-fixture\nVersion: 9.0\n"
                },
            )
            wheel = root / "aethron_edge-0.2.0-py3-none-any.whl"
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
            metadata = importlib.metadata.PathDistribution(site / "aethron_edge-9.0.dist-info")
            self.assertEqual(metadata.metadata["Name"], "foreign-fixture")
            self.assertEqual(package_check.snapshot_source_payload(site, "aethron_edge"), payload)
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload, "aethron_edge")
