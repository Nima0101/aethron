"""Two wheel builds and an offline installed HTTP/SSE consumer outside the checkout."""

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# The evidence below depends on assertions; optimized execution cannot qualify it.
if sys.flags.optimize:
    raise SystemExit("package_check_requires_assertions")

if __package__:
    from . import package_check
else:
    import package_check

ROOT = Path(__file__).resolve().parents[1]

# unittest success alone permits skipped tests and expected failures. These
# installed-suite claims require nonempty, entirely passing selected suites.
_INSTALLED_TEST_RUNNER = """
import sys
import unittest

suite = unittest.defaultTestLoader.discover(sys.argv[1], pattern=sys.argv[2])
result = unittest.TextTestRunner(verbosity=2).run(suite)
complete = (result.testsRun > 0 and result.wasSuccessful()
            and not result.skipped and not result.expectedFailures)
if not complete:
    print("installed_suite_incomplete", file=sys.stderr)
    sys.exit(1)
"""


def verify_installed_console(python: Path, work: Path, env):
    console = python.with_name("aethron-edge.exe" if os.name == "nt" else "aethron-edge")
    console_env = dict(env, PYTHONNOUSERSITE="1")
    for variable in ("PYTHONPATH", "PYTHONHOME"):
        console_env.pop(variable, None)
    result = subprocess.run(
        [str(console), "--help"],
        cwd=work,
        env=console_env,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if not result.stdout.strip():
        raise ValueError("installed_console_help_empty")


def wheel_inventory(directory: Path):
    try:
        return {wheel.name: wheel for wheel in package_check.wheel_paths(directory)}
    except (OSError, ValueError):
        raise ValueError("package_artifact_changed") from None


def run(wheelhouse: Path, output: Path, vision: bool = False):
    # Preserve earlier evidence and prevent a failed attempt from reusing its report.
    output.mkdir(parents=True, exist_ok=False)
    # Observations of selected files, not a complete or immutable build snapshot.
    input_names = [
        "scripts/edge_package_check.py",
        "scripts/package_check.py",
        "pyproject.toml",
        "integrations/edge/pyproject.toml",
        "integrations/edge/requirements-server.lock",
    ]
    if vision:
        input_names.append("integrations/edge/requirements-vision.lock")
    input_hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in input_names
    }
    payloads = {
        "aethron": package_check.snapshot_source_payload(ROOT),
        "aethron-edge": package_check.snapshot_source_payload(
            ROOT / "integrations/edge", "aethron_edge"
        ),
    }
    source_manifests = {
        distribution: {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}
        for distribution, payload in payloads.items()
    }
    env = dict(os.environ, SOURCE_DATE_EPOCH="1767225600", PIP_DISABLE_PIP_VERSION_CHECK="1")
    for variable in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(variable, None)
    hashes = {}
    # Match core packaging's per-child build/install budget. This is not a
    # whole-run deadline or a guarantee of descendant-process cleanup.
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
                timeout=180,
            )
    # Admit both inventories before reading bytes or starting installed consumers.
    first = wheel_inventory(output / "a")
    second = wheel_inventory(output / "b")
    if not first or first.keys() != second.keys():
        raise ValueError("wheel_inventory_mismatch")
    # Filename identity is necessary evidence, not authentication of wheel contents.
    from packaging.utils import InvalidWheelFilename, parse_wheel_filename

    try:
        distributions = [parse_wheel_filename(name)[0] for name in first]
    except InvalidWheelFilename:
        raise ValueError("wheel_distribution_mismatch") from None
    if sorted(distributions) != ["aethron", "aethron-edge"]:
        raise ValueError("wheel_distribution_mismatch")
    for name, wheel in sorted(first.items()):
        compared_bytes = wheel.read_bytes()
        assert compared_bytes == second[name].read_bytes(), "nonreproducible wheel"
        distribution = parse_wheel_filename(name)[0]
        package_check.validate_source_payload(
            compared_bytes, payloads[distribution], distribution.replace("-", "_")
        )
        hashes[wheel.name] = hashlib.sha256(compared_bytes).hexdigest()
    # Keep failed installed-consumer evidence with this attempt's persistent wheels.
    with package_check.reproduction_workspace(
        prefix="aethron-installed-", dir=output.resolve()
    ) as temporary:
        work = Path(temporary)
        subprocess.run(
            [sys.executable, "-m", "venv", str(work / "venv")],
            env=env,
            check=True,
            timeout=180,
        )
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
            timeout=180,
        )
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
                *[
                    first[name].resolve().as_uri() + "#sha256=" + digest
                    for name, digest in sorted(hashes.items())
                ],
            ],
            check=True,
            env=env,
            stdout=subprocess.DEVNULL,
            timeout=180,
        )
        for distribution, flag in (
            ("aethron", "--installed-payload"),
            ("aethron-edge", "--installed-edge-payload"),
        ):
            installed = subprocess.run(
                [str(python), "-I", str(ROOT / "scripts/package_check.py"), flag],
                cwd=work,
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if json.loads(installed.stdout) != source_manifests[distribution]:
                raise ValueError("installed_source_payload_mismatch")
        verify_installed_console(python, work, env)
        # Exercise new raw sensor contracts from installed wheels, outside checkout.
        for test_name in (
            "test_sensor_packets.py",
            "test_sensor_replay.py",
            "test_sensor_cloud_replay_v2.py",
            "test_sensor_cloud_inspect.py",
            "test_sensor_ros2.py",
            "test_sensor_registration.py",
            "test_sensor_raster_rectification.py",
            "test_sensor_intensity_replay.py",
            "test_sensor_intensity_inspect.py",
            "test_sensor_provider.py",
            "test_sensor_appliance.py",
            "test_sensor_radar_appliance.py",
            "test_sensor_ros_authority.py",
            "test_sensor_ros_appliance.py",
            "test_sensor_service.py",
        ):
            shutil.copyfile(ROOT / "tests/integration" / test_name, work / test_name)
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                _INSTALLED_TEST_RUNNER,
                str(work),
                "test_sensor*.py",
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
                else:
                    # Expiry is failed readiness, not permission to run consumers.
                    raise TimeoutError("installed_server_not_ready")
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
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # wait() does not stop a child on expiry. Reap this direct
                    # child, but retain shutdown failure and its workspace.
                    server.kill()
                    server.wait(timeout=10)
                    raise
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
            for name in (
                "test_rectification.py",
                "test_fisheye_rectification.py",
                "test_batched_rectification.py",
                "test_ros_lens_rectification.py",
                "test_ros_provisioned_rectification.py",
            ):
                shutil.copyfile(ROOT / "tests/integration" / name, work / name)
            subprocess.run(
                [
                    str(python),
                    "-I",
                    "-c",
                    _INSTALLED_TEST_RUNNER,
                    str(work),
                    "test*rectification.py",
                ],
                cwd=work,
                env=env,
                check=True,
                timeout=60,
            )
        try:
            final_input_hashes = {
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in input_names
            }
        except OSError:
            raise ValueError("package_input_changed") from None
        if final_input_hashes != input_hashes:
            raise ValueError("package_input_changed")
        try:
            final_inventories = [wheel_inventory(output / lane) for lane in ("a", "b")]
            for inventory in final_inventories:
                final_wheels = {
                    name: hashlib.sha256(wheel.read_bytes()).hexdigest()
                    for name, wheel in inventory.items()
                }
                if final_wheels != hashes:
                    raise ValueError("package_artifact_changed")
        except OSError:
            raise ValueError("package_artifact_changed") from None
        record = {
            "observed_input_sha256": input_hashes,
            # Source payload parity does not prove native binaries or all build inputs.
            "source_tree_bound": False,
            "source_payload_sha256": {
                distribution: hashlib.sha256(
                    json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                for distribution, manifest in source_manifests.items()
            },
            "source_payload_files": {
                distribution: len(payload) for distribution, payload in payloads.items()
            },
            "installed_source_payload": True,
            "wheels": hashes,
            "byte_identical": True,
            "installed_consumer": True,
            "console_wrapper": True,
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
