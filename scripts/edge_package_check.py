"""Two wheel builds and an offline installed HTTP/SSE consumer outside the checkout."""

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(wheelhouse: Path, output: Path, vision: bool = False):
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, SOURCE_DATE_EPOCH="1767225600", PIP_DISABLE_PIP_VERSION_CHECK="1")
    env.pop("PYTHONPATH", None)
    hashes = {}
    for lane in ("a", "b"):
        for project in (ROOT, ROOT / "integrations/edge"):
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "build",
                    "--no-isolation",
                    "--wheel",
                    "--outdir",
                    str(output / lane),
                    str(project),
                ],
                check=True,
                env=env,
                stdout=subprocess.DEVNULL,
            )
    for wheel in (output / "a").glob("*.whl"):
        assert wheel.read_bytes() == (output / "b" / wheel.name).read_bytes(), (
            "nonreproducible wheel"
        )
        hashes[wheel.name] = hashlib.sha256(wheel.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="aethron-installed-") as temporary:
        work = Path(temporary)
        subprocess.run([sys.executable, "-m", "venv", str(work / "venv")], check=True)
        python = work / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                str(wheelhouse.resolve()),
                "--require-hashes",
                "-r",
                str(ROOT / "integrations/edge/requirements-server.lock"),
            ],
            check=True,
            env=env,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                str(output.resolve() / "a"),
                "aethron-edge[server]==0.1.0",
            ],
            check=True,
            env=env,
            stdout=subprocess.DEVNULL,
        )
        # Exercise new raw sensor contracts from installed wheels, outside checkout.
        for test_name in (
            "test_sensor_packets.py",
            "test_sensor_replay.py",
            "test_sensor_ros2.py",
            "test_sensor_registration.py",
            "test_sensor_provider.py",
            "test_sensor_appliance.py",
            "test_sensor_service.py",
        ):
            shutil.copyfile(ROOT / "tests/integration" / test_name, work / test_name)
        subprocess.run(
            [
                str(python),
                "-I",
                "-m",
                "unittest",
                "discover",
                "-s",
                str(work),
                "-p",
                "test_sensor*.py",
                "-v",
            ],
            cwd=work,
            env=env,
            check=True,
            timeout=60,
        )
        shutil.copyfile(ROOT / "examples/temporal-blackout.jsonl", work / "fixture.jsonl")
        shutil.copyfile(ROOT / "examples/clients/observe.py", work / "observe.py")
        token = work / "token"
        token.write_text("c" * 64)
        token.chmod(0o600)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        config = {
            "version": 1,
            "runtime_mode": "interactive",
            "port": port,
            "profiles": [{"name": "installed", "driver": "replay", "address": "fixture.jsonl"}],
            "credentials": [
                {
                    "token_file": "token",
                    "principal": {"name": "test", "scopes": ["observe", "session:manage"]},
                }
            ],
            "status_file": "status.json",
        }
        (work / "config.json").write_text(json.dumps(config))
        with (output / "server.log").open("w") as log:
            server = subprocess.Popen(
                [
                    str(python),
                    "-I",
                    "-m",
                    "aethron_edge",
                    "serve",
                    "--config",
                    str(work / "config.json"),
                ],
                cwd=work,
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    try:
                        with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/healthz", timeout=1
                        ) as response:
                            assert response.status == 200
                        break
                    except OSError:
                        time.sleep(0.05)
                client = subprocess.run(
                    [
                        str(python),
                        "-I",
                        str(work / "observe.py"),
                        "--url",
                        f"http://127.0.0.1:{port}",
                        "--token-file",
                        str(token),
                        "--profile",
                        "installed",
                        "--limit",
                        "3",
                    ],
                    cwd=work,
                    env=env,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                rows = [json.loads(line) for line in client.stdout.splitlines()]
                assert len(rows) == 3 and all(row["current_state"] == "UNKNOWN" for row in rows)
                time.sleep(1.1)
                before = json.loads((work / "status.json").read_text())["processed"]
                continued_deadline = time.monotonic() + 10
                while time.monotonic() < continued_deadline:
                    after = json.loads((work / "status.json").read_text())["processed"]
                    if after > before:
                        break
                    time.sleep(0.1)
                assert after > before, "viewer must not own processing"
            finally:
                server.terminate()
                server.wait(timeout=10)
        if vision:
            subprocess.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--find-links",
                    str(wheelhouse.resolve()),
                    "--require-hashes",
                    "-r",
                    str(ROOT / "integrations/edge/requirements-vision.lock"),
                ],
                cwd=work,
                env=env,
                check=True,
                timeout=180,
                stdout=subprocess.DEVNULL,
            )
            shutil.copyfile(
                ROOT / "tests/integration/test_rectification.py", work / "test_rectification.py"
            )
            subprocess.run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    str(work),
                    "-p",
                    "test_rectification.py",
                    "-v",
                ],
                cwd=work,
                env=env,
                check=True,
                timeout=60,
            )
        record = {
            "wheels": hashes,
            "byte_identical": True,
            "installed_consumer": True,
            "installed_sensor_contracts": True,
            "installed_rectification": vision,
            "consumer_events": 3,
            "zero_viewer_continued": True,
            "platform": sys.platform,
            "python": sys.version.split()[0],
        }
        (output / "result.json").write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheelhouse", type=Path, default=ROOT / "build/ecosystem-phase1/wheelhouse"
    )
    parser.add_argument("--out", type=Path, default=ROOT / "build/ecosystem-phase1/package")
    parser.add_argument(
        "--vision",
        action="store_true",
        help="Also install locked vision extras and test rectification",
    )
    args = parser.parse_args()
    run(args.wheelhouse, args.out, args.vision)
