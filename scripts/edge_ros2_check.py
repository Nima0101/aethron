"""Pinned offline DDS test against installed wheels, with no checkout in the guest."""

import argparse
import hashlib
import json
import shutil
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "ros@sha256:8f687fdf084482819aa7dab48c3887331edd0d3687b219951fdb66c418316ab1"


def run(wheels, dependencies, out):
    out.mkdir(parents=True, exist_ok=True)
    bundle = out / "bundle"
    bundle.mkdir(exist_ok=True)
    for label, source in (("candidate", wheels), ("dependencies", dependencies)):
        target = bundle / label
        target.mkdir(exist_ok=True)
        for wheel in source.glob("*.whl"):
            shutil.copyfile(wheel, target / wheel.name)
    target = bundle / "tests"
    target.mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "tests/ros2/test_dds.py", target / "test_dds.py")
    for name in ("test_sensor_packets.py", "test_sensor_replay.py", "test_sensor_ros2.py"):
        shutil.copyfile(ROOT / "tests/integration" / name, target / name)
    shutil.copyfile(ROOT / "integrations/edge/ros2/requirements.lock", bundle / "requirements.lock")
    shutil.copyfile(
        ROOT / "integrations/edge/ros2/container_check.py", bundle / "container_check.py"
    )
    hashes = {
        str(p.relative_to(bundle)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(bundle.glob("*/*.whl"))
    }
    (bundle / "wheels.json").write_text(json.dumps(hashes, indent=2) + "\n")
    name = "aethron-ros-check-" + uuid.uuid4().hex[:12]
    command = [
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--name",
        name,
        "--platform",
        "linux/arm64",
        "--network",
        "none",
        "--read-only",
        "--user",
        "10001:10001",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "512m",
        "--cpus",
        "2",
        "--pids-limit",
        "96",
        "--tmpfs",
        "/tmp:exec,size=160m",
        "-e",
        "ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST",
        "-e",
        "ROS_LOG_DIR=/tmp/ros-logs",
        "-v",
        str(bundle.resolve()) + ":/bundle:ro",
        IMAGE,
        "python3",
        "/bundle/container_check.py",
    ]
    try:
        with (out / "dds.log").open("w") as log:
            completed = subprocess.run(
                command, stdout=log, stderr=subprocess.STDOUT, timeout=180, check=False
            )
        if completed.returncode:
            raise SystemExit("ROS DDS check failed; inspect " + str(out / "dds.log"))
        records = [
            json.loads(line.removeprefix("AETHRON_ROS_RESULT "))
            for line in (out / "dds.log").read_text().splitlines()
            if line.startswith("AETHRON_ROS_RESULT ")
        ]
        if len(records) != 1:
            raise RuntimeError("missing_ros_result")
        record = dict(records[0], image=IMAGE, platform="linux/arm64")
        (out / "result.json").write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(record, sort_keys=True))
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheels", type=Path, required=True)
    parser.add_argument("--dependencies", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.wheels, args.dependencies, args.out)
