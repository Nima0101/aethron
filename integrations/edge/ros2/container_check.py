"""Offline installed consumer entry point inside a pinned ROS image."""

import hashlib
import json
import os
import subprocess
import sys
import venv
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    if os.geteuid() != 10001:
        raise RuntimeError("unexpected_container_uid")
    bundle = Path("/bundle")
    hashes = json.loads((bundle / "wheels.json").read_text())
    for relative, expected in hashes.items():
        path = bundle / relative
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("wheel_hash_mismatch")
    venv.create("/tmp/aethron-ros", with_pip=False, system_site_packages=True)
    python = "/tmp/aethron-ros/bin/python"
    pip = next((bundle / "dependencies").glob("pip-*.whl"))
    bootstrap = (
        "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); "
        'sys.argv[0]="pip"; runpy.run_module("pip",run_name="__main__")'
    )
    env = dict(os.environ, PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_CACHE_DIR="1")
    subprocess.run(
        [
            python,
            "-c",
            bootstrap,
            str(pip),
            "install",
            "--no-index",
            "--find-links",
            str(bundle / "dependencies"),
            "--require-hashes",
            "-r",
            str(bundle / "requirements.lock"),
            "-r",
            str(bundle / "requirements-vision.lock"),
        ],
        check=True,
        env=env,
    )
    subprocess.run(
        [
            python,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            *map(str, sorted((bundle / "candidate").glob("*.whl"))),
        ],
        check=True,
        env=env,
    )
    subprocess.run([python, "/bundle/tests/provision_ros_sdk.py"], check=True, env=env)
    subprocess.run(
        [python, "-m", "unittest", "discover", "-s", str(bundle / "tests"), "-v"],
        cwd="/tmp",
        check=True,
        env=env,
        timeout=60,
    )
    report = {
        "installed_ros_dds": True,
        "isolated_sdk_provisioned": True,
        "signed_cli_loss_restart_source_rewind": True,
        "installed_signed_ros_cli_http_sse": True,
        "installed_raw_fisheye_dds": True,
        "installed_signed_raw_depth_cli_http_sse": True,
        "signed_configuration_tamper_denied": True,
        "uid": os.geteuid(),
        "payloads": "original synthetic Image/CameraInfo/PointCloud2",
        "hardware_qualified": False,
        "diagnostic_instrumentation": os.environ.get("AETHRON_ROS_TEST_DIAGNOSTICS") == "1",
        "scene_state": "UNKNOWN",
        "network": "none",
        "python": sys.version.split()[0],
        "wheels": hashes,
        "packages": {
            n: ET.parse("/opt/ros/jazzy/share/" + n + "/package.xml").getroot().findtext("version")
            for n in ("rclpy", "sensor_msgs", "rmw_fastrtps_cpp")
        },
    }
    print("AETHRON_ROS_RESULT " + json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
