"""Source parity must not admit writes to another distribution's metadata."""

import importlib.metadata
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


class WheelForeignMetadata(unittest.TestCase):
    def test_foreign_metadata_rejects_before_payload_reads(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for name in (
                    "foreign-1.0.dist-info/METADATA",
                    "FOREIGN-1.0.DIST-INFO/RECORD",
                    "foreign-1.0.dist-info/",
                    "foreign.egg-info/PKG-INFO",
                    "foreign.egg-info",
                    "FOREIGN.EGG-INFO/",
                    f"{package}_extra-1.0.dist-info/METADATA",
                ):
                    with self.subTest(package=package, layout=layout, name=name):
                        raw, payload = wheel_bytes(package, {layout + name: b"# fixture\n"})
                        with patch.object(
                            zipfile.ZipFile, "read", autospec=True, side_effect=zipfile.ZipFile.read
                        ) as read:
                            with self.assertRaisesRegex(
                                ValueError, "^wheel_source_payload_mismatch$"
                            ):
                                package_check.validate_source_payload(raw, payload, package)
                            read.assert_not_called()

    def test_own_metadata_and_nested_examples_pass(self):
        for package in ("aethron", "aethron_edge"):
            with self.subTest(package=package):
                raw, payload = wheel_bytes(
                    package,
                    {
                        f"{package}-0.2.0.dist-info/licenses/NOTICE": b"notice\n",
                        f"{package}-0.2.0.data/purelib/{package}-0.2.0.dist-info/top_level.txt": package,
                        f"{package}/examples/foreign.egg-info/PKG-INFO": b"example\n",
                        f"{package}/examples/foreign-1.0.dist-info/METADATA": b"example\n",
                        f"{package}-0.2.0.data/data/share/foreign.egg-info": b"example\n",
                        "foreign.dist-info.txt": b"example\n",
                    },
                )
                package_check.validate_source_payload(raw, payload, package)

    def test_installer_overwrites_foreign_version_without_source_change(self):
        # Only inert metadata in a disposable venv. No foreign code is imported.
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
            metadata = site / "foreign_fixture-1.0.dist-info"
            metadata.mkdir()
            contents = "Metadata-Version: 2.1\nName: foreign-fixture\nVersion: {}\n"
            (metadata / "METADATA").write_text(contents.format("1.0"), encoding="utf-8")

            def version():
                return next(
                    distribution.version
                    for distribution in importlib.metadata.distributions(path=[str(site)])
                    if distribution.metadata["Name"] == "foreign-fixture"
                )

            self.assertEqual(version(), "1.0")
            raw, payload = wheel_bytes(
                "aethron_edge",
                {
                    "aethron_edge-0.2.0.data/purelib/foreign_fixture-1.0.dist-info/METADATA": contents.format(
                        "2.0"
                    )
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
            self.assertEqual(version(), "2.0")
            self.assertEqual(package_check.snapshot_source_payload(site, "aethron_edge"), payload)
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload, "aethron_edge")
