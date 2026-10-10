"""Synthetic wheel contract comparison; never imports product code."""

import argparse
import configparser
import email.parser
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

BACKENDS = {
    "setuptools": (
        "setuptools.build_meta",
        '[tool.setuptools.packages.find]\ninclude=["probe_pkg*"]\n[tool.setuptools.package-data]\nprobe_pkg=["*.json", "*.pxd"]\n',
    ),
    "hatchling": ("hatchling.build", '[tool.hatch.build.targets.wheel]\npackages=["probe_pkg"]\n'),
    "flit_core": ("flit_core.buildapi", '[tool.flit.module]\nname="probe_pkg"\n'),
    "uv_build": ("uv_build", '[tool.uv.build-backend]\nmodule-name="probe_pkg"\nmodule-root=""\n'),
}
PAYLOAD = {
    "probe_pkg/__init__.py": b'"""Synthetic packaging fixture."""\ndef main():\n    print("synthetic-ok")\n',
    "probe_pkg/schema.json": b'{"synthetic":true}\n',
    "probe_pkg/_bounds.pxd": b"ctypedef int synthetic_value\n",
}


def validate_wheel(wheel: Path, license_bytes: bytes) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        files = {info.filename for info in archive.infolist() if not info.is_dir()}
        assert {p for p in files if not p.startswith("probe_package-0.0.1.dist-info/")} == set(
            PAYLOAD
        ), names
        for p, data in PAYLOAD.items():
            assert archive.read(p) == data
        metadata_name = next(p for p in names if p.endswith(".dist-info/METADATA"))
        metadata = email.parser.BytesParser().parsebytes(archive.read(metadata_name))
        for field, value in [
            ("Name", "probe-package"),
            ("Version", "0.0.1"),
            ("Requires-Python", ">=3.9"),
            ("License-Expression", "GPL-3.0-only"),
        ]:
            assert metadata[field] == value, (field, metadata[field])
        assert metadata.get_all("Requires-Dist", []) == []
        license_name = next(p for p in names if p.endswith("/licenses/LICENSE"))
        assert archive.read(license_name) == license_bytes
        entries = configparser.ConfigParser()
        entries.read_string(
            archive.read(next(p for p in names if p.endswith("/entry_points.txt"))).decode()
        )
        assert entries["console_scripts"]["probe-package"] == "probe_pkg:main"
        return names


def main() -> None:
    if sys.flags.optimize:
        raise SystemExit("probe_requires_assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--backend", choices=["setuptools", "hatchling", "flit_core", "uv_build"])
    options = parser.parse_args()
    ROOT = options.out.resolve()
    ROOT.mkdir(parents=True, exist_ok=False)
    TOOLS = options.tools.resolve()
    LICENSE = Path(__file__).resolve().parents[1] / "LICENSE"
    results = []
    for name, (backend, config) in BACKENDS.items():
        if options.backend and options.backend != name:
            continue
        project = ROOT / (name + "-fixture")
        project.mkdir(exist_ok=False)
        for path, body in PAYLOAD.items():
            p = project / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)
        (project / "README.md").write_text("Synthetic packaging parity fixture.\n")
        (project / "LICENSE").write_bytes(LICENSE.read_bytes())
        (project / "unrelated-private-note.txt").write_text("Must not enter wheel.\n")
        (project / "pyproject.toml").write_text(
            '[build-system]\nrequires=[]\nbuild-backend="'
            + backend
            + '"\n[project]\nname="probe-package"\nversion="0.0.1"\ndescription="Synthetic fixture"\nreadme="README.md"\nrequires-python=">=3.9"\nlicense="GPL-3.0-only"\nlicense-files=["LICENSE"]\ndependencies=[]\n[project.scripts]\nprobe-package="probe_pkg:main"\n'
            + config
        )
        hashes = []
        durations = []
        payloads = []
        for lane in ["a", "b"]:
            out = project / lane
            out.mkdir()
            command = [
                sys.executable,
                "-I",
                "-c",
                "import sys,importlib;sys.path.insert(0,sys.argv[1]);print(importlib.import_module(sys.argv[2]).build_wheel(sys.argv[3]))",
                str(TOOLS),
                backend,
                str(out),
            ]
            start = time.perf_counter()
            result = subprocess.run(
                command,
                cwd=project,
                env=dict(
                    os.environ,
                    SOURCE_DATE_EPOCH="1767225600",
                    PATH=str(TOOLS / "bin") + os.pathsep + os.environ.get("PATH", ""),
                ),
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            durations.append(time.perf_counter() - start)
            (project / (lane + ".log")).write_text(result.stdout + result.stderr)
            result.check_returncode()
            wheels = list(out.glob("*.whl"))
            assert len(wheels) == 1
            wheel = wheels[0]
            hashes.append(hashlib.sha256(wheel.read_bytes()).hexdigest())
            payloads.append(validate_wheel(wheel, LICENSE.read_bytes()))
        assert hashes[0] == hashes[1], name
        environment = project / "installed"
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(environment)],
            check=True,
            timeout=30,
            capture_output=True,
        )
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        installed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "--python",
                str(python),
                "install",
                "--no-index",
                "--no-deps",
                str(wheel),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        (project / "install.log").write_text(installed.stdout + installed.stderr)
        installed.check_returncode()
        console = environment / (
            "Scripts/probe-package.exe" if os.name == "nt" else "bin/probe-package"
        )
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        run = subprocess.run(
            [str(console)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        assert run.returncode == 0 and run.stdout == "synthetic-ok\n", (name, run)
        results.append(
            {
                "backend": name,
                "sha256": hashes[0],
                "identical_builds": True,
                "contract_parity": True,
                "console_wrapper": True,
                "wall_seconds": durations,
                "members": payloads[0],
            }
        )
        (ROOT / "results.json").write_text(json.dumps(results, indent=2) + "\n")
        print(name, "PASS", durations, flush=True)


if __name__ == "__main__":
    main()
