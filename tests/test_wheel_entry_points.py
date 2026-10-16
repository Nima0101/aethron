"""Launcher metadata must not escape source-wheel admission."""

import os
import subprocess
import tempfile
import unittest
import venv
from pathlib import Path

from test_wheel_data_destinations import wheel_bytes

from scripts import package_check


class WheelEntryPoints(unittest.TestCase):
    def test_undeclared_or_malformed_entry_points_reject(self):
        for package, command, target in (
            ("aethron", "aethron", "aethron.__main__:main"),
            ("aethron_edge", "aethron-edge", "aethron_edge.cli:main"),
        ):
            valid = f"[console_scripts]\n{command} = {target}\n"
            for contents in (
                "[console_scripts]\nfixture-tool = fixture:main\n",
                valid + "fixture-tool = fixture:main\n",
                f"[console_scripts]\n{command} = fixture:main\n",
                f"[console_scripts]\n{command.upper()} = {target}\n",
                valid + "[gui_scripts]\nfixture-tool = fixture:main\n",
                valid + f"{command} = {target}\n",
                valid + "[console_scripts]\n",
                f"[DEFAULT]\n{command} = {target}\n[console_scripts]\n",
                valid + "[fixture.plugin]\nfixture = fixture:main\n",
                "[console_scripts]\n",
                "not an INI file",
                "",
                b"\xff",
                valid + "#" * 65536,
            ):
                for layout in (
                    "",
                    f"{package}-0.2.0.data/purelib/",
                    f"{package}-0.2.0.data/platlib/",
                ):
                    with self.subTest(
                        package=package, contents=repr(contents)[:100], layout=layout
                    ):
                        raw, payload = wheel_bytes(
                            package,
                            {layout + f"{package}-0.2.0.dist-info/entry_points.txt": contents},
                        )
                        with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                            package_check.validate_source_payload(raw, payload, package)

    def test_declared_entry_points_and_nested_resources_pass(self):
        for package, command, target in (
            ("aethron", "aethron", "aethron.__main__:main"),
            ("aethron_edge", "aethron-edge", "aethron_edge.cli:main"),
        ):
            for newline in ("\n", "\r\n"):
                with self.subTest(package=package, newline=newline):
                    raw, payload = wheel_bytes(
                        package,
                        {
                            f"{package}-0.2.0.dist-info/entry_points.txt": f"# generated{newline}[console_scripts]{newline}{command} = {target}{newline}",
                            f"{package}/examples/example.dist-info/entry_points.txt": b"example",
                        },
                    )
                    package_check.validate_source_payload(raw, payload, package)

    def test_multiple_entry_point_metadata_files_reject(self):
        raw, payload = wheel_bytes(
            "aethron",
            {
                f"{name}.dist-info/entry_points.txt": b"[console_scripts]\naethron = aethron.__main__:main\n"
                for name in ("aethron-0.2.0", "other-1.0")
            },
        )
        with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
            package_check.validate_source_payload(raw, payload)

    def test_installer_creates_undeclared_launcher_from_metadata(self):
        # Prove the installer behavior with an inert, uniquely named wrapper.
        # Do not replace environment tools or execute the generated launcher.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            scripts = environment / ("Scripts" if os.name == "nt" else "bin")
            python = scripts / ("python.exe" if os.name == "nt" else "python")
            raw, payload = wheel_bytes(
                "aethron",
                {
                    "aethron-0.2.0.dist-info/entry_points.txt": b"[console_scripts]\naethron-fixture-wrapper = aethron.module:main\n"
                },
            )
            wheel = root / "aethron-0.2.0-py3-none-any.whl"
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
            launcher = "aethron-fixture-wrapper" + (".exe" if os.name == "nt" else "")
            self.assertTrue((scripts / launcher).is_file())
            with self.assertRaisesRegex(ValueError, "^wheel_source_payload_mismatch$"):
                package_check.validate_source_payload(raw, payload)
