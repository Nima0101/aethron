"""Build a locally signed ARM64 Linux SIL image, without provisioning the host.

The test key is explicitly supplied, never embedded in the guest or published.
This creates a VM acceptance artifact, not a qualified physical-device image.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
MAVLINK_LOCK = ROOT / "integrations/edge/requirements-mavlink-linux-arm64-py312.lock"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def command(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def stage_inputs(context, *, ros=False, startup_trace=False):
    for name in (
        "Guest.Containerfile",
        "sign_bundle.py",
        "boot_probe.py",
        "sensor_probe.py",
        "ros_boot_probe.py",
        "update_probe.py",
        "appliance.json",
    ):
        shutil.copyfile(HERE / name, context / name)
    shutil.copyfile(HERE / "aethron-sil-probe.service", context / "probe.service")
    shutil.copyfile(HERE.parent / "systemd/aethron.service", context / "aethron.service")
    shutil.copyfile(ROOT / "examples/temporal-blackout.jsonl", context / "fixture.jsonl")
    shutil.copyfile(
        ROOT / "integrations/edge/requirements-server.lock", context / "requirements.lock"
    )
    raw = ROOT / "examples/sensors/recorded-depth"
    shutil.copyfile(raw / "depth.aeraw", context / "raw-depth.aeraw")
    shutil.copyfile(raw / "sensor.json", context / "raw-depth.json")
    config = json.loads((context / "appliance.json").read_text())
    provenance = {"sensor-replay": "recorded", "sensor-ros": "external_unverified"}
    sensor_profiles = {
        p["name"]: provenance[p["driver"]] for p in config["profiles"] if p["driver"] in provenance
    }
    (context / "probe-profiles.json").write_text(json.dumps(sensor_profiles, sort_keys=True))
    if ros:
        stage_ros_inputs(context)
    if startup_trace:
        for name in ("aethron.service", "ros-runtime.service"):
            unit = context / name
            if unit.exists():
                unit.write_text(
                    unit.read_text()
                    .replace(
                        "Environment=PYTHONDONTWRITEBYTECODE=1",
                        "Environment=PYTHONDONTWRITEBYTECODE=1\nEnvironment=AETHRON_STARTUP_TRACE=1",
                    )
                    .replace("StandardError=journal\n", "StandardError=journal+console\n")
                )
    return sensor_profiles


def stage_ros_inputs(context):
    for name in ("ros_fixture.py", "ros_lifecycle_probe.py", "provision_ros_sdk.py"):
        shutil.copyfile(HERE / name, context / name)
    shutil.copyfile(HERE / "RosGuest.Containerfile", context / "Guest.Containerfile")
    shutil.copyfile(HERE / "aethron-ros-check.service", context / "ros-check.service")
    # Reuse the appliance sandbox; only the fixed test config/environment differ.
    service = (context / "aethron.service").read_text()
    service = service.replace(
        "ExecStart=/opt/aethron/venv/bin/aethron-edge run --config /opt/aethron/appliance.json --update-store /var/lib/aethron-updates",
        "ExecStart=/opt/aethron/venv/bin/python -I -m aethron_edge run --config /opt/aethron/ros-appliance.json",
    ).replace("Restart=on-failure", "Restart=no")
    service = (
        service.replace(
            "Environment=PYTHONDONTWRITEBYTECODE=1",
            "Environment=PYTHONDONTWRITEBYTECODE=1\nEnvironmentFile=/opt/aethron/venv/ros.env\nEnvironment=ROS_LOG_DIR=/run/aethron-ros/logs",
        )
        .replace("RuntimeDirectory=aethron", "RuntimeDirectory=aethron-ros")
        .replace(
            "ReadWritePaths=/var/lib/aethron /run/aethron",
            "ReadWritePaths=/var/lib/aethron /run/aethron-ros",
        )
    )
    service = service.replace("StandardError=journal", "StandardError=journal+console")
    (context / "ros-runtime.service").write_text(service)
    probe = (
        (context / "probe.service")
        .read_text()
        .replace(
            "After=aethron.service",
            "After=aethron.service aethron-ros-check.service\nWants=aethron-ros-check.service",
        )
        .replace("/usr/local/bin/python", "/opt/aethron/venv/bin/python")
    )
    (context / "probe.service").write_text(probe)
    config = json.loads((context / "appliance.json").read_text())
    config.update(
        profiles=[
            {
                "name": "ros-depth",
                "driver": "sensor-ros",
                "address": "/aethron/depth",
                "sensor_manifest": "ros-depth.json",
                "lighting": "zero_visible",
            }
        ],
        status_file="/var/lib/aethron/ros-status.json",
        port=8743,
    )
    (context / "ros-appliance.json").write_text(json.dumps(config, indent=2) + "\n")
    manifest = json.loads((ROOT / "examples/sensors/ros-depth/sensor.json").read_text())
    manifest.update(version=2, renewal="software_fixture", valid_for_ns=4_000_000_000)
    (context / "ros-depth.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (context / "ros-required").write_text("systemd_lifecycle_only\n")
    shutil.copyfile(
        ROOT / "integrations/edge/ros2/requirements.lock", context / "requirements.lock"
    )


def check_ros_runtime(guest_id):
    test = ROOT / "tests/ros2/test_runtime_image.py"
    test_hash = digest(test)
    command(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--user",
            "aethron",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "-v",
            str(test) + ":/test_runtime_image.py:ro",
            "-e",
            "LD_LIBRARY_PATH=/opt/ros/jazzy/lib:/opt/ros/jazzy/lib/aarch64-linux-gnu",
            guest_id,
            "/opt/aethron/venv/bin/python",
            "-I",
            "-B",
            "/test_runtime_image.py",
            "-v",
        ],
        timeout=30,
    )
    return test_hash


def stage_mavlink_inputs(context, dependencies):
    """Validate the complete optional closure before adding any build inputs."""
    lock = MAVLINK_LOCK.read_text()
    expected = {}
    for line in lock.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = re.fullmatch(r"([a-z]+)==([0-9.]+) --hash=sha256:([0-9a-f]{64})", line)
        if match is None or match[1] in expected:
            raise ValueError("invalid_mavlink_dependencies")
        expected[match[1]] = (match[2], match[3])
    if set(expected) != {"pymavlink", "fastcrc", "lxml"}:
        raise ValueError("invalid_mavlink_dependencies")
    sources = sorted(dependencies.iterdir())
    hashes, names = {}, set()
    for source in sources:
        name = source.name.split("-", 1)[0]
        if (
            name not in expected
            or name in names
            or source.is_symlink()
            or not source.is_file()
            or not source.name.endswith(".whl")
            or not source.name.startswith(name + "-" + expected[name][0] + "-")
            or digest(source) != expected[name][1]
        ):
            raise ValueError("invalid_mavlink_dependencies")
        names.add(name)
        hashes[source.name] = expected[name][1]
    if names != set(expected):
        raise ValueError("invalid_mavlink_dependencies")
    for source in sources:
        shutil.copyfile(source, context / "dependencies" / source.name)
    with (context / "requirements.lock").open("a") as stream:
        stream.write("\n" + lock)
    return hashes


def stage_mavlink_probe(context):
    """Add an explicit synthetic boot gate only to the optional SDK image."""
    shutil.copyfile(HERE / "telemetry_boot_probe.py", context / "telemetry_boot_probe.py")
    shutil.copyfile(HERE / "aethron-telemetry-check.service", context / "telemetry-check.service")
    config = json.loads((context / "appliance.json").read_text())
    config["runtime_mode"] = "appliance"
    config["telemetry"] = [
        {
            "name": "sil-telemetry",
            "system_id": 1,
            "component_id": 1,
            "port": 14550,
            "clock_policy_file": "/var/lib/aethron-telemetry/policy.json",
            "replay_file": "/var/lib/aethron-telemetry/replay.db",
        }
    ]
    (context / "telemetry-appliance.json").write_text(json.dumps(config, sort_keys=True))
    recipe = context / "Guest.Containerfile"
    text = recipe.read_text().replace(
        "COPY sign_bundle.py /tmp/sign.py",
        "COPY telemetry-appliance.json /opt/aethron/\n"
        "COPY telemetry_boot_probe.py /opt/aethron-sil/\n"
        "COPY telemetry-check.service /etc/systemd/system/aethron-telemetry-check.service\n"
        "COPY sign_bundle.py /tmp/sign.py",
    )
    text += (
        "\nRUN mkdir /var/lib/aethron-telemetry && chown aethron:aethron /var/lib/aethron-telemetry "
        "&& chmod 0700 /var/lib/aethron-telemetry "
        "&& runuser -u aethron -- /opt/aethron/venv/bin/python -I -B "
        "/opt/aethron-sil/telemetry_boot_probe.py provision "
        "&& systemctl enable aethron-telemetry-check.service\n"
    )
    recipe.write_text(text)
    service = context / "probe.service"
    service.write_text(
        service.read_text().replace(
            "[Unit]",
            "[Unit]\nAfter=aethron-telemetry-check.service\nWants=aethron-telemetry-check.service",
        )
    )
    (context / "telemetry-required").write_text("synthetic_direct_sdk\n")
    recipe.write_text(
        recipe.read_text().replace(
            "COPY telemetry_boot_probe.py /opt/aethron-sil/",
            "COPY telemetry_boot_probe.py telemetry-required /opt/aethron-sil/",
        )
    )


def check_mavlink_runtime(guest_id):
    test = ROOT / "tests/mavlink/linux_runtime.py"
    command(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec,size=32m",
            "--user",
            "aethron",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "-v",
            str(test) + ":/linux_runtime.py:ro",
            guest_id,
            "/opt/aethron/venv/bin/python",
            "-I",
            "-B",
            "/linux_runtime.py",
            "-v",
        ],
        timeout=30,
    )
    return digest(test)


def prepare(
    output,
    wheels,
    key,
    tool_image=None,
    ros_dependencies=None,
    mavlink_dependencies=None,
    startup_trace=False,
):
    if mavlink_dependencies is not None and ros_dependencies is None:
        raise ValueError("mavlink_requires_python312_ros_guest")
    output = output.resolve()
    if not output.is_relative_to(ROOT / "build"):
        raise ValueError("output_must_be_in_own_build_directory")
    output.mkdir(parents=True, exist_ok=True)
    if (output / "rootfs.raw").exists():
        raise ValueError("use_fresh_output_to_preserve_previous_evidence")
    if not key.is_file() or (key.stat().st_mode & 0o077):
        raise ValueError("explicit_test_key_with_private_permissions_required")
    env = dict(os.environ, BUILDX_CONFIG=str(ROOT / "build/ecosystem-phase1/buildx"))
    if tool_image is None:
        tool_image = "aethron-phase1-vm-tools:local"
        command(
            [
                "docker",
                "buildx",
                "build",
                "--load",
                "--platform",
                "linux/arm64",
                "-t",
                tool_image,
                "-f",
                str(HERE / "Tools.Containerfile"),
                str(HERE),
            ],
            env=env,
        )
    tool_id = command(
        ["docker", "image", "inspect", "--format", "{{.Id}}", tool_image],
        capture_output=True,
        text=True,
    ).stdout.strip()
    context = output / "context"
    context.mkdir()
    sensor_profiles = stage_inputs(
        context, ros=ros_dependencies is not None, startup_trace=startup_trace
    )
    dependency_hashes = {}
    if ros_dependencies is not None:
        (context / "dependencies").mkdir()
        for source in sorted(ros_dependencies.glob("*.whl")):
            dependency_hashes[source.name] = digest(source)
            shutil.copyfile(source, context / "dependencies" / source.name)
        if not dependency_hashes:
            raise ValueError("ros_offline_dependencies_required")
    mavlink_hashes = (
        stage_mavlink_inputs(context, mavlink_dependencies)
        if mavlink_dependencies is not None
        else {}
    )
    if mavlink_hashes:
        stage_mavlink_probe(context)
    (context / "wheels").mkdir()
    wheel_hashes = {}
    for name in ("aethron-0.2.0-py3-none-any.whl", "aethron_edge-0.1.0-py3-none-any.whl"):
        source = wheels / name
        wheel_hashes[name] = digest(source)
        shutil.copyfile(source, context / "wheels" / name)
    # The existing immutable tool image ID is recorded; build argument uses its
    # locally verified tag because BuildKit treats bare sha256 IDs as remote names.
    guest = (
        "aethron-ros-guest:local" if ros_dependencies is not None else "aethron-phase1-guest:local"
    )
    command(
        [
            "docker",
            "buildx",
            "build",
            "--load",
            "--platform",
            "linux/arm64",
            "--build-arg",
            "TOOL_IMAGE=" + tool_image,
            "--secret",
            "id=testkey,src=" + str(key.resolve()),
            "-t",
            guest,
            "-f",
            str(context / "Guest.Containerfile"),
            str(context),
        ],
        env=env,
    )
    guest_id = command(
        ["docker", "image", "inspect", "--format", "{{.Id}}", guest], capture_output=True, text=True
    ).stdout.strip()
    runtime_check = check_ros_runtime(guest_id) if ros_dependencies is not None else None
    mavlink_check = check_mavlink_runtime(guest_id) if mavlink_hashes else None
    packages = command(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            guest_id,
            "dpkg-query",
            "-W",
            "-f=${Package}=${Version}\n",
        ],
        capture_output=True,
        text=True,
    ).stdout
    (output / "dpkg.txt").write_text(packages)
    shutil.copyfile(HERE / "make-root.sh", output / "make-root.sh")
    name = "aethron-export-" + uuid.uuid4().hex[:12]
    command(["docker", "create", "--name", name, guest_id], capture_output=True)
    try:
        exporting = subprocess.Popen(["docker", "export", name], stdout=subprocess.PIPE)
        try:
            command(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "-i",
                    "-v",
                    str(output) + ":/out",
                    tool_id,
                    "sh",
                    "/out/make-root.sh",
                ],
                stdin=exporting.stdout,
            )
        finally:
            exporting.stdout.close()
            code = exporting.wait(timeout=60)
        if code:
            raise RuntimeError("image_export_failed")
    finally:
        command(["docker", "rm", name], capture_output=True)
    manifest = {
        "schema_version": 1,
        "kind": "test_only_linux_sil",
        "tool_image": tool_id,
        "guest_image": guest_id,
        "wheels": wheel_hashes,
        "dpkg_sha256": digest(output / "dpkg.txt"),
        "files": {n: digest(output / n) for n in ("kernel", "initrd", "rootfs.raw")},
        "templates": {
            str(p.relative_to(ROOT)): digest(p) for p in sorted(HERE.iterdir()) if p.is_file()
        },
        "hardware_qualified": False,
        "startup_trace": startup_trace,
        "sensor_profiles": sensor_profiles,
        "ros_lifecycle_required": ros_dependencies is not None,
        "ros_dependencies": dependency_hashes,
        "mavlink_dependencies": mavlink_hashes,
        "mavlink_boot_required": bool(mavlink_hashes),
        "mavlink_lock_sha256": digest(MAVLINK_LOCK) if mavlink_hashes else None,
        "mavlink_runtime_consumer_test_sha256": mavlink_check,
        "ros_runtime_consumer_test_sha256": runtime_check,
    }
    (output / "image-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    )
    command(
        [
            "openssl",
            "pkeyutl",
            "-sign",
            "-rawin",
            "-inkey",
            str(key),
            "-in",
            str(output / "image-manifest.json"),
            "-out",
            str(output / "image-manifest.sig"),
        ]
    )
    command(
        ["openssl", "pkey", "-in", str(key), "-pubout", "-out", str(output / "test-only.pub")],
        capture_output=True,
    )
    print("Built signed local SIL image. No service installed on host; no hardware qualification.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--wheels", type=Path, required=True)
    parser.add_argument("--test-key", type=Path, required=True)
    parser.add_argument(
        "--tool-image", help="Reuse explicitly selected locally installed tool image"
    )
    parser.add_argument(
        "--ros-dependencies",
        type=Path,
        help="Build Jazzy/Python 3.12 guest with this offline locked wheelhouse",
    )
    parser.add_argument(
        "--mavlink-dependencies",
        type=Path,
        help="Optional hash-locked CPython3.12 ARM64 MAVLink wheelhouse (ROS guest only)",
    )
    parser.add_argument(
        "--startup-trace",
        action="store_true",
        help="Opt-in bounded startup stage timings to guest console",
    )
    args = parser.parse_args()
    prepare(
        args.out,
        args.wheels,
        args.test_key,
        args.tool_image,
        args.ros_dependencies,
        args.mavlink_dependencies,
        startup_trace=args.startup_trace,
    )


if __name__ == "__main__":
    main()
