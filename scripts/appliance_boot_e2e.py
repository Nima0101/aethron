"""Boot an actual signed Linux guest image, offline, through its service manager."""

import argparse
import hashlib
import json
import re
import subprocess
import time
import uuid
from pathlib import Path


def inspect_evidence(serial: Path):
    events = []
    for line in serial.read_text(errors="replace").splitlines():
        match = re.search(r"AETHRON_SIL (\{.*\})", line)
        if match:
            events.append(json.loads(match[1]))
    results = {e["boot"]: e for e in events if e["event"] == "result"}
    passed = (
        1 in results
        and 2 in results
        and results[1]["processing_continued"]
        and results[2]["processing_continued"]
        and results[2]["seconds"] >= 3600
        and results[2]["worker_fault_injected"]
        and results[2].get("processing_resumed_after_fault")
        and results[2].get("updated_runtime_processing")
    )
    return {
        "status": "passed" if passed else "failed",
        "kind": "emulated_linux_boot_sil",
        "hardware_qualified": False,
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


def run(image: Path, tool_image: str, timeout: int):
    for name in ("kernel", "initrd", "rootfs.raw"):
        if not (image / name).is_file():
            raise ValueError("missing_image_artifact")
    manifest = verify_image(image)
    before = manifest["files"]
    tool_image = tool_image or manifest["tool_image"]
    cidfile = image.resolve() / ("container-" + uuid.uuid4().hex + ".cid")
    serial = image / "serial.log"
    # No NIC, shared directory, forwarded port, SSH, login or provisioner is
    # attached to the guest. The host sees its serial observation channel only.
    command = [
        "docker",
        "run",
        "--rm",
        "--cidfile",
        str(cidfile),
        "--network",
        "none",
        "--cpus",
        "2",
        "--memory",
        "1500m",
        "-v",
        str(image.resolve()) + ":/out",
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
        "/out/kernel",
        "-initrd",
        "/out/initrd",
        "-append",
        "console=ttyAMA0 root=/dev/vda rw init=/sbin/init systemd.show_status=false",
        "-drive",
        "file=/out/rootfs.raw,format=raw,if=virtio",
    ]
    start = time.monotonic()
    code = None
    try:
        with serial.open("w") as output:
            process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
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
    if process.poll() is None:
        process.wait(timeout=30)
    report = inspect_evidence(serial)
    report.update(
        image_before=before,
        elapsed_seconds=time.monotonic() - start,
        exit_code=code,
        image_manifest_sha256=file_digest(image / "image-manifest.json"),
        wheels=manifest["wheels"],
        tool_image=tool_image,
    )
    (image / "result.json").write_text(json.dumps(report, indent=2) + "\n")
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
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    if args.inspect:
        print(json.dumps(inspect_evidence(args.image / "serial.log"), indent=2))
    else:
        run(args.image, args.tool_image, args.timeout)
