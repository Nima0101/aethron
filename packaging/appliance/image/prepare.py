"""Build a locally signed ARM64 Linux SIL image, without provisioning the host.

The test key is explicitly supplied, never embedded in the guest or published.
This creates a VM acceptance artifact, not a qualified physical-device image.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def command(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def prepare(output, wheels, key, tool_image=None):
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
    for name in (
        "Guest.Containerfile",
        "sign_bundle.py",
        "boot_probe.py",
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
    (context / "wheels").mkdir()
    wheel_hashes = {}
    for name in ("aethron-0.2.0-py3-none-any.whl", "aethron_edge-0.1.0-py3-none-any.whl"):
        source = wheels / name
        wheel_hashes[name] = digest(source)
        shutil.copyfile(source, context / "wheels" / name)
    # The existing immutable tool image ID is recorded; build argument uses its
    # locally verified tag because BuildKit treats bare sha256 IDs as remote names.
    guest = "aethron-phase1-guest:local"
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--wheels", type=Path, required=True)
    parser.add_argument("--test-key", type=Path, required=True)
    parser.add_argument(
        "--tool-image", help="Reuse explicitly selected locally installed tool image"
    )
    args = parser.parse_args()
    prepare(args.out, args.wheels, args.test_key, args.tool_image)
