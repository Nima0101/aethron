"""Build wheels twice and install into a fresh environment outside the source tree."""

import hashlib
import importlib.metadata
import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# Optimized execution removes the assertions that establish this evidence.
if sys.flags.optimize:
    raise SystemExit("package_check_requires_assertions")

ROOT = Path(__file__).resolve().parents[1]


SOURCE_SUFFIXES = (".py", ".pxd", ".json")


def snapshot_source_payload(root, package_name="aethron"):
    payload = {}
    package = root / package_name
    if package.is_symlink():
        raise ValueError("invalid_source_payload_file")
    if not package.exists():
        raise ValueError("empty_source_payload")

    def unreadable(error):
        raise error

    for directory, directories, files in os.walk(package, onerror=unreadable):
        for name in directories:
            path = Path(directory) / name
            if path.is_symlink() or path.suffix in SOURCE_SUFFIXES:
                raise ValueError("invalid_source_payload_file")
        for name in files:
            path = Path(directory) / name
            if path.suffix in SOURCE_SUFFIXES:
                if path.is_symlink() or not path.is_file():
                    raise ValueError("invalid_source_payload_file")
                payload[path.relative_to(root).as_posix()] = path.read_bytes()
    if not payload:
        raise ValueError("empty_source_payload")
    return payload


def validate_source_payload(wheel_bytes, payload, package_name="aethron"):
    with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as wheel:
        names = [
            name
            for name in wheel.namelist()
            if name.startswith(package_name + "/") and name.endswith(SOURCE_SUFFIXES)
        ]
        if len(names) != len(set(names)) or set(names) != set(payload):
            raise ValueError("wheel_source_payload_mismatch")
        if any(wheel.read(name) != payload[name] for name in names):
            raise ValueError("wheel_source_payload_mismatch")


def installed_source_manifest(package_name="aethron", distribution="aethron"):
    package = Path(importlib.metadata.distribution(distribution).locate_file(package_name))
    package.resolve().relative_to(Path(sys.prefix).resolve())
    return {
        name: hashlib.sha256(data).hexdigest()
        for name, data in snapshot_source_payload(package.parent, package_name).items()
    }


def run():
    with tempfile.TemporaryDirectory(prefix="aethron-wheel-") as directory:
        temp = Path(directory)
        source_payload = snapshot_source_payload(ROOT)
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
        validate_source_payload(compared_bytes, source_payload)
        source_manifest = {
            name: hashlib.sha256(data).hexdigest() for name, data in source_payload.items()
        }
        source_payload_sha256 = hashlib.sha256(
            json.dumps(source_manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
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
        installed = subprocess.run(
            [str(python), "-I", str(Path(__file__).resolve()), "--installed-payload"],
            cwd=temp,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if json.loads(installed.stdout) != source_manifest:
            raise ValueError("installed_source_payload_mismatch")
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
        # Consumers must not invalidate the artifacts qualified by the comparison.
        # Keep the original digest; never re-label replacement bytes as verified.
        for wheel in (a, b):
            if sorted(wheel.parent.glob("*.whl")) != [wheel]:
                raise ValueError("wheel_artifacts_changed")
            if wheel.is_symlink() or not wheel.is_file():
                raise ValueError("wheel_artifacts_changed")
            if wheel.read_bytes() != compared_bytes:
                raise ValueError("wheel_artifacts_changed")
        print(
            json.dumps(
                {
                    "wheel": a.name,
                    "sha256": wheel_sha256,
                    "byte_identical": True,
                    "isolated_install": True,
                    "console_wrapper": True,
                    "dependency_installation": False,
                    "source_payload_files": len(source_manifest),
                    "source_payload_sha256": source_payload_sha256,
                    "installed_source_payload": True,
                }
            )
        )


if __name__ == "__main__":
    if sys.argv[1:] == ["--installed-payload"]:
        print(json.dumps(installed_source_manifest(), sort_keys=True))
    else:
        run()
