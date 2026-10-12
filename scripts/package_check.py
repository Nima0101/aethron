"""Build wheels twice and install into a fresh environment outside the source tree."""

import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import zipfile
from importlib.metadata import version
from pathlib import Path

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
        a = next((temp / "a").glob("*.whl"))
        b = next((temp / "b").glob("*.whl"))
        assert a.read_bytes() == b.read_bytes(), "wheel builds differ"
        with zipfile.ZipFile(a) as archive:
            assert {name for name in archive.namelist() if name.startswith("qualification/")} == {
                f"qualification/{path.name}" for path in (ROOT / "qualification").glob("*.py")
            }, "qualification runtime module inventory differs"
        subprocess.run([sys.executable, "-m", "venv", str(temp / "consumer")], check=True)
        python = temp / "consumer" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(a)],
            cwd=temp,
            check=True,
            stdout=subprocess.DEVNULL,
        )
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
        qualification = subprocess.run(
            [
                str(python),
                "-I",
                str(ROOT / "scripts/qualification_consumer.py"),
                str(ROOT / "qualification/fixtures/assessment-vectors-v1.json"),
            ],
            cwd=temp,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        qualification_result = json.loads(qualification.stdout)
        assert qualification_result == {"assessment_vectors": 10, "isolated_install": True}
        print(
            json.dumps(
                {
                    "wheel": a.name,
                    "sha256": hashlib.sha256(a.read_bytes()).hexdigest(),
                    "byte_identical": True,
                    "isolated_install": True,
                    "runtime_dependencies": 0,
                    "python": platform.python_version(),
                    "platform": platform.platform(),
                    "build_tools": {
                        name: version(name) for name in ("build", "setuptools", "wheel")
                    },
                    "qualification": qualification_result,
                }
            )
        )


if __name__ == "__main__":
    run()
