"""Run installed external consumers; failure is a failing gate, never a skip."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/edge_package_check.py")], check=True, cwd=ROOT
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests/integration",
            "-p",
            "test_edge_http.py",
        ],
        check=True,
        cwd=ROOT,
    )
