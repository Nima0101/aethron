"""Real wheel reproduction across checkout permissions and builder umasks."""

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
class EdgeWheelModes(unittest.TestCase):
    def test_checkout_modes_do_not_change_wheel(self):
        project = ROOT / "integrations/edge"
        wheels = []
        with tempfile.TemporaryDirectory() as temporary:
            for index, (mode, mask) in enumerate(((0o664, 0o002), (0o600, 0o077))):
                source = Path(temporary) / str(index)
                source.mkdir()
                shutil.copytree(
                    project / "aethron_edge",
                    source / "aethron_edge",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
                for name in ("pyproject.toml", "LICENSE", "README.md", "_build.py", "MANIFEST.in"):
                    if (project / name).exists():
                        shutil.copyfile(project / name, source / name)
                for path in source.rglob("*"):
                    if path.is_file():
                        path.chmod(mode)
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
                    env=dict(os.environ, SOURCE_DATE_EPOCH="1767225600"),
                    umask=mask,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                wheel = next((source / "dist").glob("*.whl"))
                wheels.append(wheel.read_bytes())
                # Building must not change the source checkout's permissions.
                self.assertEqual((source / "aethron_edge/__init__.py").stat().st_mode & 0o777, mode)
                with zipfile.ZipFile(wheel) as archive:
                    self.assertEqual(archive.testzip(), None)
            self.assertTrue(wheels[0] == wheels[1], "wheel bytes depend on checkout mode/umask")
