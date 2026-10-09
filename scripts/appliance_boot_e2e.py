"""Boot an actual signed Linux guest image, offline, through its service manager."""

import argparse
import hashlib
import json
import re
import subprocess
import time
import uuid
from pathlib import Path


def sensor_evidence_valid(result, required, *, recovery):
    rows = result.get("sensor_profiles", {})
    if not isinstance(rows, dict):
        return False
    for name, evidence in required.items():
        row = rows.get(name)
        if not isinstance(row, dict) or row.get("source_evidence") != evidence:
            return False
        if row.get("processing_observed") is not True or row.get("processing_at_end") is not True:
            return False
        for key in ("batches_observed", "unavailable_samples", "fault_samples", "invalid_samples"):
            if type(row.get(key)) is not int or not 0 <= row[key] <= 2**53 - 1:
                return False
        if row["batches_observed"] == 0:
            return False
        if recovery and (
            row.get("processing_resumed_after_fault") is not True
            or row.get("updated_runtime_processing") is not True
        ):
            return False
    return True


def ros_lifecycle_valid(result):
    row = result.get("ros_lifecycle")
    if not isinstance(row, dict):
        return False
    return (
        all(
            row.get(key) is True
            for key in (
                "processing_observed",
                "source_expiry_verified",
                "reconnect_cannot_revive",
                "explicit_restart_revalidated",
                "source_rewind_verified",
                "clock_restore_cannot_revive",
            )
        )
        and row.get("service_manager") == "systemd"
        and isinstance(row.get("boot_id"), str)
        and bool(row["boot_id"])
        and row.get("hardware_qualified") is False
        and row.get("continuous_availability_qualified") is False
        and row.get("scene_state") == "UNKNOWN"
        and type(row.get("viewers")) is int
        and row["viewers"] == 0
    )


def telemetry_boot_valid(result):
    row = result.get("telemetry_boot")
    return (
        isinstance(row, dict)
        and isinstance(row.get("boot_id"), str)
        and bool(row["boot_id"])
        and row.get("kind") == "synthetic_direct_sdk"
        and row.get("hardware_qualified") is False
        and row.get("continuous_availability_qualified") is False
        and all(
            row.get(key) is True
            for key in (
                "grant_preserved",
                "counter_advanced",
                "signed_packet_accepted",
                "duplicate_rejected",
            )
        )
    )


def inspect_evidence(
    serial: Path,
    *,
    required_sensors=None,
    require_ros_lifecycle=False,
    require_telemetry_boot=False,
    exit_code=0,
):
    events = []
    for line in serial.read_text(errors="replace").splitlines():
        match = re.search(r"AETHRON_SIL (\{.*\})", line)
        if match:
            events.append(json.loads(match[1]))
    required_sensors = {} if required_sensors is None else required_sensors
    results = {e["boot"]: e for e in events if e["event"] == "result"}
    passed = (
        exit_code == 0
        and not any(e.get("event") == "probe_failed" for e in events)
        and 1 in results
        and 2 in results
        and results[1]["processing_continued"] is True
        and results[2]["processing_continued"] is True
        and results[2]["seconds"] >= 3600
        and results[2]["worker_fault_injected"] is True
        and results[2].get("processing_resumed_after_fault") is True
        and results[2].get("updated_runtime_processing") is True
        and sensor_evidence_valid(results[1], required_sensors, recovery=False)
        and sensor_evidence_valid(results[2], required_sensors, recovery=True)
        and (
            not require_ros_lifecycle
            or (
                ros_lifecycle_valid(results[1])
                and ros_lifecycle_valid(results[2])
                and results[1]["ros_lifecycle"]["boot_id"] != results[2]["ros_lifecycle"]["boot_id"]
            )
        )
        and (
            not require_telemetry_boot
            or (
                telemetry_boot_valid(results[1])
                and telemetry_boot_valid(results[2])
                and results[1]["telemetry_boot"].get("prior_boot") == "initial"
                and results[2]["telemetry_boot"].get("prior_boot") == "different"
                and results[1]["telemetry_boot"]["boot_id"]
                != results[2]["telemetry_boot"]["boot_id"]
                and (
                    not require_ros_lifecycle
                    or all(
                        results[i]["telemetry_boot"]["boot_id"]
                        == results[i]["ros_lifecycle"]["boot_id"]
                        for i in (1, 2)
                    )
                )
            )
        )
        and all(
            type(results[2].get("drops", {}).get(key)) is int and results[2]["drops"][key] >= 0
            for key in ("capture_sequence_gaps", "mailbox_overwritten", "mailbox_rejected")
        )
    )
    return {
        "status": "passed" if passed else "failed",
        "kind": "emulated_linux_boot_sil",
        "hardware_qualified": False,
        "required_sensor_profiles": required_sensors,
        "ros_lifecycle_required": require_ros_lifecycle,
        "mavlink_boot_required": require_telemetry_boot,
        "events": events,
        "serial_sha256": hashlib.sha256(serial.read_bytes()).hexdigest(),
    }


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_image(image: Path):
    signature = subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-rawin",
            "-inkey",
            str(image / "test-only.pub"),
            "-in",
            str(image / "image-manifest.json"),
            "-sigfile",
            str(image / "image-manifest.sig"),
        ],
        capture_output=True,
        timeout=10,
        check=False,
    )
    if signature.returncode:
        raise ValueError("invalid_image_signature")
    manifest = json.loads((image / "image-manifest.json").read_text())
    if set(manifest["files"]) != {"kernel", "initrd", "rootfs.raw"}:
        raise ValueError("invalid_image_manifest")
    if any(file_digest(image / name) != value for name, value in manifest["files"].items()):
        raise ValueError("invalid_image_hash")
    return manifest


def new_run_directory(image: Path, output: Path | None = None):
    image = image.resolve()
    if output is None:
        parent = image / "runs"
        if parent.is_symlink():
            raise ValueError("invalid_run_parent")
        parent.mkdir(exist_ok=True)
        output = parent / uuid.uuid4().hex
    output = output.resolve()
    if image.is_relative_to(output):
        raise ValueError("run_directory_must_not_replace_image")
    output.mkdir(parents=True, exist_ok=False)
    return output


def create_overlay(image: Path, output: Path, tool_image: str):
    overlay = output / "rootfs.qcow2"
    if overlay.exists() or overlay.is_symlink():
        raise FileExistsError("preserve_existing_overlay")
    with (output / "overlay-create.log").open("x") as log:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "-v",
                str(image.resolve()) + ":/base:ro",
                "-v",
                str(output.resolve()) + ":/out",
                tool_image,
                "qemu-img",
                "create",
                "-f",
                "qcow2",
                "-F",
                "raw",
                "-b",
                "/base/rootfs.raw",
                "/out/rootfs.qcow2",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
            timeout=30,
        )
    return overlay


def vm_command(image: Path, output: Path, tool_image: str):
    # No NIC, shared directory, forwarded port, SSH, login or provisioner is
    # attached to the guest. The host sees its serial observation channel only.
    return [
        "docker",
        "run",
        "--rm",
        "--cidfile",
        str(output / "container.cid"),
        "--network",
        "none",
        "--cpus",
        "2",
        "--memory",
        "1500m",
        "-v",
        str(image.resolve()) + ":/base:ro",
        "-v",
        str(output.resolve()) + ":/out",
        tool_image,
        "qemu-system-aarch64",
        "-machine",
        "virt-10.0",
        "-cpu",
        "cortex-a72",
        "-accel",
        "tcg",
        "-smp",
        "2",
        "-m",
        "768",
        "-nographic",
        "-nic",
        "none",
        "-kernel",
        "/base/kernel",
        "-initrd",
        "/base/initrd",
        "-append",
        "console=ttyAMA0 root=/dev/vda rw init=/sbin/init systemd.show_status=false",
        "-drive",
        "file=/out/rootfs.qcow2,format=qcow2,if=virtio",
    ]


def run(image: Path, tool_image: str, timeout: int, output: Path | None = None):
    image = image.resolve()
    manifest = verify_image(image)
    before = manifest["files"]
    manifest_hash = file_digest(image / "image-manifest.json")
    requested_tool = tool_image or manifest["tool_image"]
    tool_image = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", requested_tool],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout.strip()
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", tool_image):
        raise ValueError("invalid_tool_image_id")
    output = new_run_directory(image, output)
    (output / "request.json").write_text(
        json.dumps(
            {
                "image_manifest_sha256": manifest_hash,
                "image_before": before,
                "tool_image": tool_image,
                "sensor_profiles": manifest.get("sensor_profiles", {}),
                "ros_lifecycle_required": manifest.get("ros_lifecycle_required", False),
                "mavlink_boot_required": manifest.get("mavlink_boot_required", False),
            },
            indent=2,
        )
        + "\n"
    )
    create_overlay(image, output, tool_image)
    cidfile = output / "container.cid"
    serial = output / "serial.log"
    command = vm_command(image, output, tool_image)
    print("Boot evidence directory: " + str(output), flush=True)
    start = time.monotonic()
    code = None
    process = None
    try:
        with serial.open("x") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            last_event = start
            event_count = 0
            while process.poll() is None:
                time.sleep(0.5)
                trace = serial.read_text(errors="replace")
                observed = trace.count("AETHRON_SIL ")
                if observed > event_count:
                    last_event, event_count = time.monotonic(), observed
                if (
                    '"event": "probe_failed"' in trace
                    or time.monotonic() - start > timeout
                    or time.monotonic() - last_event > 300
                ):
                    code = 124
                    break
            if code is None:
                code = process.returncode
    finally:
        # Only this invocation's container, never a global prune/process search.
        if cidfile.exists():
            cid = cidfile.read_text().strip()
            if re.fullmatch(r"[a-f0-9]{64}", cid):
                subprocess.run(
                    ["docker", "rm", "-f", cid], capture_output=True, timeout=30, check=False
                )
    if process is not None and process.poll() is None:
        process.wait(timeout=30)
    report = inspect_evidence(
        serial,
        required_sensors=manifest.get("sensor_profiles", {}),
        require_ros_lifecycle=manifest.get("ros_lifecycle_required", False),
        require_telemetry_boot=manifest.get("mavlink_boot_required", False),
        exit_code=code,
    )
    after = {name: file_digest(image / name) for name in before}
    unchanged = after == before and file_digest(image / "image-manifest.json") == manifest_hash
    if not unchanged:
        report["status"] = "failed"
    report.update(
        image_before=before,
        image_after=after,
        base_unchanged=unchanged,
        overlay_sha256=file_digest(output / "rootfs.qcow2"),
        elapsed_seconds=time.monotonic() - start,
        exit_code=code,
        image_manifest_sha256=manifest_hash,
        wheels=manifest["wheels"],
        tool_image=tool_image,
    )
    (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] != "passed":
        raise SystemExit("FAIL: boot/soak evidence incomplete; retained serial log")
    print(
        "PASS: real emulated Linux boot, offline reboot and >=1h synthetic soak; no hardware qualification"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--tool-image", default=None)
    parser.add_argument("--timeout", type=int, default=4800)
    parser.add_argument(
        "--out",
        type=Path,
        help="Fresh per-run evidence directory (default: image/runs/<unique-id>)",
    )
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    if args.inspect:
        if args.out is None:
            parser.error("--inspect requires --out naming a retained run")
        manifest = verify_image(args.image)
        result = json.loads((args.out / "result.json").read_text())
        inspected = inspect_evidence(
            args.out / "serial.log",
            required_sensors=manifest.get("sensor_profiles", {}),
            require_ros_lifecycle=manifest.get("ros_lifecycle_required", False),
            require_telemetry_boot=manifest.get("mavlink_boot_required", False),
            exit_code=result["exit_code"],
        )
        if result["base_unchanged"] is not True or result["image_manifest_sha256"] != file_digest(
            args.image / "image-manifest.json"
        ):
            inspected["status"] = "failed"
        print(json.dumps(inspected, indent=2))
    else:
        run(args.image, args.tool_image, args.timeout, args.out)
