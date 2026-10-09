"""An edited native header must invalidate a previously compiled extension."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

source = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="aethron-header-rebuild-") as directory:
    project = Path(directory) / "project"
    shutil.copytree(source, project, ignore=shutil.ignore_patterns("*.egg-info", "__pycache__"))
    command = [sys.executable, "setup.py", "build_ext"]
    first = subprocess.run(
        command, cwd=project, capture_output=True, text=True, check=False, timeout=120
    )
    if first.returncode:
        raise RuntimeError("initial_native_build_failed: " + first.stderr)
    header = project / "aethron_raster_native/kernel.hpp"
    header.write_text("#error aethron_header_rebuild_probe\n")
    second = subprocess.run(
        command, cwd=project, capture_output=True, text=True, check=False, timeout=120
    )
    if (
        second.returncode == 0
        or "aethron_header_rebuild_probe" not in second.stdout + second.stderr
    ):
        raise AssertionError("changed_header_did_not_invalidate_compiled_extension")
print("header dependency rebuild PASS; owned temporary project removed")
