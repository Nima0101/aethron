"""Core wheels must reproduce across checkout modes and builder umasks."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == "posix", "POSIX checkout permission counterexample")
class CoreWheelModes(unittest.TestCase):
    def test_checkout_modes_do_not_change_wheel(self):
        wheels = []
        with tempfile.TemporaryDirectory() as temporary:
            for index, (mode, executable, mask) in enumerate(
                ((0o664, 0o775, 0o002), (0o600, 0o700, 0o077))
            ):
                source = Path(temporary) / str(index)
                source.mkdir()
                shutil.copytree(
                    ROOT / "aethron",
                    source / "aethron",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.so", "*.pyd"),
                )
                for name in (
                    "pyproject.toml",
                    "setup.py",
                    "LICENSE",
                    "NOTICE",
                    "README.md",
                    "_build.py",
                    "MANIFEST.in",
                ):
                    if (ROOT / name).exists():
                        shutil.copyfile(ROOT / name, source / name)
                # Preserve the executable/non-executable distinction too, without
                # executing this synthetic package member or changing the checkout.
                script = source / "aethron/models/mode_fixture.json"
                script.write_bytes(b'{"synthetic": true}\n')
                original = {}
                for path in source.rglob("*"):
                    if path.is_file():
                        path.chmod(executable if path == script else mode)
                        original[path] = (path.read_bytes(), path.stat().st_mode & 0o777)
                env = dict(
                    os.environ, SOURCE_DATE_EPOCH="1767225600", AETHRON_BUILD_NATIVE_BOUNDS="0"
                )
                env.pop("PYTHONPATH", None)
                env.pop("PYTHONHOME", None)
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "build",
                        "--no-isolation",
                        "--wheel",
                        "--outdir",
                        str(source / "dist"),
                        str(source),
                    ],
                    env=env,
                    umask=mask,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                wheel = next((source / "dist").glob("*.whl"))
                wheels.append(wheel.read_bytes())
                self.assertEqual(
                    {p: (p.read_bytes(), p.stat().st_mode & 0o777) for p in original}, original
                )
                with zipfile.ZipFile(wheel) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(
                        archive.read("aethron/models/mode_fixture.json"), original[script][0]
                    )
                    for name in ("aethron/__init__.py", "aethron/models/rules.json"):
                        self.assertEqual(archive.getinfo(name).external_attr >> 16 & 0o777, 0o644)
                    self.assertEqual(
                        archive.getinfo("aethron/models/mode_fixture.json").external_attr >> 16
                        & 0o777,
                        0o755,
                    )
            self.assertTrue(wheels[0] == wheels[1], "wheel bytes depend on checkout mode/umask")
