"""Clean local clone builds and installs the committed candidate; no public operation."""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(wheelhouse):
    area = ROOT / "build/ecosystem-phase1"
    area.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clean-edge-", dir=area) as temporary:
        clone = Path(temporary) / "source"
        subprocess.run(
            ["git", "clone", "--no-local", str(ROOT), str(clone)], check=True, capture_output=True
        )
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        subprocess.run([sys.executable, "scripts/verify.py"], cwd=clone, env=env, check=True)
        subprocess.run(
            [sys.executable, "scripts/check_ecosystem_plan.py", "--self-test"],
            cwd=clone,
            env=env,
            check=True,
        )
        subprocess.run(
            [
                sys.executable,
                "scripts/edge_package_check.py",
                "--wheelhouse",
                str(wheelhouse.resolve()),
                "--out",
                str(area / "clean-package"),
            ],
            cwd=clone,
            env=env,
            check=True,
        )
        print("PASS: committed clean clone and installed consumer; local artifacts only")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheelhouse", type=Path, default=ROOT / "build/ecosystem-phase1/wheelhouse"
    )
    run(parser.parse_args().wheelhouse)
