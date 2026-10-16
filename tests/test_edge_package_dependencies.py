"""Check real offline installations, including requirements unused by imports."""

import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.edge_package_check import verify_installed_dependencies


class InstalledDependencies(unittest.TestCase):
    def test_missing_incompatible_and_satisfied_requirements(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            env = dict(os.environ, PIP_DISABLE_PIP_VERSION_CHECK="1")
            for name in ("PYTHONPATH", "PYTHONHOME"):
                env.pop(name, None)
            subprocess.run(
                [sys.executable, "-m", "venv", str(work / "venv")],
                check=True,
                capture_output=True,
                env=env,
                timeout=30,
            )
            python = work / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

            def install(name, version, requires=""):
                wheel = work / f"{name}-{version}-py3-none-any.whl"
                info = f"{name}-{version}.dist-info"
                with zipfile.ZipFile(wheel, "w") as archive:
                    archive.writestr(
                        info + "/METADATA",
                        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n" + requires,
                    )
                    archive.writestr(
                        info + "/WHEEL",
                        "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
                    )
                    archive.writestr(info + "/RECORD", "")
                subprocess.run(
                    [
                        str(python),
                        "-I",
                        "-m",
                        "pip",
                        "install",
                        "--no-index",
                        "--no-deps",
                        str(wheel),
                    ],
                    cwd=work,
                    env=env,
                    check=True,
                    capture_output=True,
                    timeout=30,
                )

            install(
                "packaging_probe",
                "1.0",
                "Requires-Dist: packaging-probe-dependency>=2\n"
                "Requires-Dist: inactive-probe; python_version < '2'\n",
            )
            with self.assertRaises(subprocess.CalledProcessError) as missing:
                verify_installed_dependencies(python, work, env)
            self.assertIn("packaging-probe-dependency", missing.exception.stdout)
            self.assertIn("not installed", missing.exception.stdout)
            install("packaging_probe_dependency", "1.0")
            with self.assertRaises(subprocess.CalledProcessError) as incompatible:
                verify_installed_dependencies(python, work, env)
            self.assertIn("packaging-probe-dependency>=2", incompatible.exception.stdout)
            install("packaging_probe_dependency", "2.0")
            verify_installed_dependencies(python, work, env)
