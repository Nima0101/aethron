"""Foreign extension modules must not escape wheel package ownership checks."""

import importlib.machinery
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


class WheelForeignExtensions(unittest.TestCase):
    def test_foreign_extensions_reject_before_payload_reads(self):
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                for name in (
                    "foreign.so",
                    "foreign.abi3.so",
                    "foreign.cpython-313-x86_64-linux-gnu.so",
                    "foreign.pyd",
                    "foreign.cp313-win_amd64.pyd",
                    "foreign/__init__.so",
                    "foreign/namespace/module.pyd",
                    "FOREIGN/MODULE.SO",
                    "FOREIGN/MODULE.PYD",
                    f"{package}_extra/module.so",
                    "aethron/module.so" if package == "aethron_edge" else "aethron_edge/module.pyd",
                ):
                    with self.subTest(package=package, layout=layout, name=name):
                        raw, payload = wheel_bytes(package, {layout + name: b"inert fixture"})
                        with patch.object(
                            zipfile.ZipFile, "read", autospec=True, side_effect=zipfile.ZipFile.read
                        ) as read:
                            with self.assertRaisesRegex(
                                ValueError, "^wheel_source_payload_mismatch$"
                            ):
                                package_check.validate_source_payload(raw, payload, package)
                            read.assert_not_called()

    def test_owned_extensions_and_nonimport_resources_remain_admissible(self):
        # Ownership admission does not certify native binary/source parity.
        for package in ("aethron", "aethron_edge"):
            for layout in ("", f"{package}-0.2.0.data/purelib/", f"{package}-0.2.0.data/platlib/"):
                with self.subTest(package=package, layout=layout):
                    raw, payload = wheel_bytes(
                        package,
                        {
                            layout + f"{package}/_bounds.abi3.so": b"inert fixture",
                            layout + f"{package}/_bounds.cp313-win_amd64.pyd": b"inert fixture",
                            f"{package}-0.2.0.dist-info/licenses/example.so": b"resource",
                            f"{package}-0.2.0.data/data/share/example.pyd": b"resource",
                            f"{package}-0.2.0.data/headers/example.so": b"resource",
                            "foreign/module.so.txt": b"resource",
                            "foreign.pyd/notes.txt": b"resource",
                            "foreign.so/": b"",
                        },
                    )
                    package_check.validate_source_payload(raw, payload, package)

    def test_installer_adds_foreign_extension_shadowing_existing_source(self):
        # Never load a binary: inert text is installed in a disposable venv,
        # and PathFinder only selects the module's spec without executing it.
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
            module = "fixture_foreign"
            source = site / (module + ".py")
            source.write_bytes(b"VALUE = 1\n")
            finder = importlib.machinery.PathFinder
            self.assertEqual(finder.find_spec(module, [str(site)]).origin, str(source))
            extension = module + importlib.machinery.EXTENSION_SUFFIXES[0]
            raw, payload = wheel_bytes(
                "aethron_edge",
                {"aethron_edge-0.2.0.data/platlib/" + extension: b"inert fixture"},
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
            # The fixture venv uses the host's standard purelib/platlib layout.
            self.assertEqual((site / extension).read_bytes(), b"inert fixture")
            self.assertEqual(source.read_bytes(), b"VALUE = 1\n")
            finder.invalidate_caches()
            spec = finder.find_spec(module, [str(site)])
            self.assertEqual(spec.origin, str(site / extension))
            self.assertIsInstance(spec.loader, importlib.machinery.ExtensionFileLoader)
            self.assertEqual(package_check.snapshot_source_payload(site, "aethron_edge"), payload)
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload, "aethron_edge")
