"""Build wheels twice and install into a fresh environment outside the source tree."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Optimized execution removes the assertions that establish this evidence.
if sys.flags.optimize:
    raise SystemExit("package_check_requires_assertions")

ROOT = Path(__file__).resolve().parents[1]


def run():
    with tempfile.TemporaryDirectory(prefix="aethron-wheel-") as directory:
        temp = Path(directory)
        env = dict(os.environ, SOURCE_DATE_EPOCH="1767225600")
        for name in ("a", "b"):
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "build",
                    "--no-isolation",
                    "--wheel",
                    "--outdir",
                    str(temp / name),
                ],
                cwd=ROOT,
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
            )
        first = sorted((temp / "a").glob("*.whl"))
        second = sorted((temp / "b").glob("*.whl"))
        if len(first) != 1 or len(second) != 1 or first[0].name != second[0].name:
            raise ValueError("wheel_inventory_mismatch")
        a, b = first[0], second[0]
        compared_bytes = a.read_bytes()
        assert compared_bytes == b.read_bytes(), "wheel builds differ"
        wheel_sha256 = hashlib.sha256(compared_bytes).hexdigest()
        subprocess.run([sys.executable, "-m", "venv", str(temp / "consumer")], check=True)
        python = temp / "consumer" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--force-reinstall",
                "--require-hashes",
                a.resolve().as_uri() + "#sha256=" + wheel_sha256,
            ],
            cwd=temp,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        console = python.with_name("aethron.exe" if os.name == "nt" else "aethron")
        console_env = dict(os.environ, PYTHONNOUSERSITE="1")
        for variable in ("PYTHONPATH", "PYTHONHOME"):
            console_env.pop(variable, None)
        help_result = subprocess.run(
            [str(console), "--help"],
            cwd=temp,
            env=console_env,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert help_result.stdout.strip(), "console help is empty"
        result = subprocess.run(
            [str(python), "-I", "-m", "aethron", "demo"],
            cwd=temp,
            check=True,
            capture_output=True,
            text=True,
        )
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        assert len(rows) == 22
        person = next(r["result"] for r in rows if r["scenario"] == "person-zero-visible-thermal")
        assert person["recommendation"]["action"] == "STOP"
        assert next(c for c in person["claims"] if c["capability"] == "human_presence")[
            "sources"
        ] == ["thermal_person"]
        temporal = subprocess.run(
            [
                str(python),
                "-I",
                "-m",
                "aethron",
                "replay",
                str(ROOT / "examples/temporal-blackout.jsonl"),
            ],
            cwd=temp,
            check=True,
            capture_output=True,
            text=True,
        )
        tracked = [json.loads(line) for line in temporal.stdout.splitlines()]
        assert len(tracked) == 24
        assert len({r["tracks"][0]["id"] for r in tracked}) == 1
        assert tracked[-1]["tracks"][0]["sources"] == ["depth", "lwir", "radar"]
        print(
            json.dumps(
                {
                    "wheel": a.name,
                    "sha256": wheel_sha256,
                    "byte_identical": True,
                    "isolated_install": True,
                    "console_wrapper": True,
                    "dependency_installation": False,
                }
            )
        )


if __name__ == "__main__":
    run()
