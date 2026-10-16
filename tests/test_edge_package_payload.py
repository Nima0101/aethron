"""Read actual installed package bytes from an isolated environment, without imports."""

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
import venv
import zipfile
from pathlib import Path

from scripts import edge_package_check, package_check


class InstalledEdgePayload(unittest.TestCase):
    def test_isolated_manifest_reads_both_distributions_and_detects_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / "venv"
            venv.EnvBuilder(with_pip=False).create(environment)
            python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            result = subprocess.run(
                [str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            site = Path(result.stdout.strip())
            for package, version, flag in (
                ("aethron", "0.2.0", "--installed-payload"),
                ("aethron_edge", "0.1.0", "--installed-edge-payload"),
            ):
                with self.subTest(package=package):
                    payload = {
                        package
                        + "/__init__.py": b"raise RuntimeError('must not import package')\n",
                        package + "/module.py": b"VALUE = 1\n",
                    }
                    for name, data in payload.items():
                        path = site / name
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(data)
                    metadata = site / (package + "-" + version + ".dist-info")
                    metadata.mkdir()
                    (metadata / "METADATA").write_text(
                        "Metadata-Version: 2.1\nName: "
                        + package.replace("_", "-")
                        + "\nVersion: "
                        + version
                        + "\n"
                    )
                    shadow = root / package
                    shadow.mkdir()
                    (shadow / "__init__.py").write_text("raise RuntimeError('shadow')\n")

                    def manifest(flag=flag):
                        result = subprocess.run(
                            [str(python), "-I", str(Path(package_check.__file__).resolve()), flag],
                            cwd=root,
                            env=dict(os.environ, PYTHONPATH=str(root)),
                            check=True,
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )
                        return json.loads(result.stdout)

                    expected = {
                        name: hashlib.sha256(data).hexdigest() for name, data in payload.items()
                    }
                    self.assertEqual(manifest(), expected)
                    (site / package / "module.py").write_bytes(b"VALUE = 2\n")
                    changed = manifest()
                    self.assertNotEqual(changed, expected)
                    self.assertEqual(
                        changed[package + "/module.py"], hashlib.sha256(b"VALUE = 2\n").hexdigest()
                    )
                    (site / package / "module.py").unlink()
                    self.assertNotIn(package + "/module.py", manifest())
                    (site / package / "extra.py").write_bytes(b"# stale\n")
                    self.assertIn(package + "/extra.py", manifest())
                    for suffix in (".PY", ".JsOn", ".PxD"):
                        with self.subTest(suffix=suffix):
                            name = package + "/unexpected" + suffix
                            path = site / name
                            path.write_bytes(b"# unexpected source\n")
                            self.assertEqual(
                                manifest().get(name),
                                hashlib.sha256(b"# unexpected source\n").hexdigest(),
                            )
                            path.write_bytes(b"# changed source\n")
                            self.assertEqual(
                                manifest().get(name),
                                hashlib.sha256(b"# changed source\n").hexdigest(),
                            )
                            path.unlink()
                            self.assertNotIn(name, manifest())

    def test_real_installed_console_runs_outside_checkout_and_missing_launcher_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = root / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            wheel = root / "aethron_edge-0.1.0-py3-none-any.whl"
            metadata = "aethron_edge-0.1.0.dist-info/"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr("aethron_edge/__init__.py", "")
                archive.writestr(
                    "aethron_edge/cli.py",
                    "import sys\ndef main():\n"
                    "    assert sys.argv[1:] == ['--help']\n"
                    "    print('usage: synthetic aethron-edge')\n",
                )
                archive.writestr(
                    metadata + "METADATA",
                    "Metadata-Version: 2.1\nName: aethron-edge\nVersion: 0.1.0\n",
                )
                archive.writestr(
                    metadata + "WHEEL",
                    "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
                )
                archive.writestr(
                    metadata + "entry_points.txt",
                    "[console_scripts]\naethron-edge = aethron_edge.cli:main\n",
                )
                archive.writestr(metadata + "RECORD", "")
            subprocess.run(
                [str(python), "-I", "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            shadow = root / "aethron_edge"
            shadow.mkdir()
            (shadow / "__init__.py").write_text("raise RuntimeError('caller package shadow')\n")
            env = dict(os.environ, PYTHONPATH=str(root), PYTHONHOME=str(root / "invalid-home"))
            edge_package_check.verify_installed_console(python, root, env)
            launcher = python.with_name("aethron-edge.exe" if os.name == "nt" else "aethron-edge")
            launcher.unlink()
            with self.assertRaises(FileNotFoundError):
                edge_package_check.verify_installed_console(python, root, env)
