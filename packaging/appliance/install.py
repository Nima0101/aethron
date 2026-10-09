"""Offline root-directory installer; never starts a service on the build Mac."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def install(root: Path, bundle: Path, key: Path):
    from aethron_edge.runtime.updates import verify_bundle

    verify_bundle(bundle, key)
    if root.resolve() == Path("/") and sys.platform != "linux":
        raise ValueError("Linux target required")
    target = root / "opt/aethron"
    if target.exists():
        raise ValueError("use transactional update for existing installation")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle, target)
    verify_bundle(target, key)
    etc = root / "etc/aethron"
    etc.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(key, etc / "trust.pub")
    units = root / "etc/systemd/system"
    units.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(__file__).parent / "systemd/aethron.service", units / "aethron.service")
    wants = units / "multi-user.target.wants"
    wants.mkdir(exist_ok=True)
    (wants / "aethron.service").symlink_to("../aethron.service")
    # Account creation/device-group provisioning belongs to image/package scripts;
    # modifying a foreign host's account database is never an implicit operation.
    return {"installed": True, "enabled": True, "started": False, "requires_account": "aethron"}


def provision_telemetry(name, timestamp_floor):
    """Explicit Linux administrator action; execute only as the installed service UID.

    Never create accounts, copy keys, change existing modes, initialize on boot,
    retry a failed child or remove state. Fixed installed paths are administrator-owned.
    """
    try:
        if (
            sys.platform != "linux"
            or os.geteuid() != 0
            or not isinstance(name, str)
            or re.fullmatch(r"[a-z0-9-]{1,48}", name) is None
            or type(timestamp_floor) is not int
            or not 0 <= timestamp_floor < (1 << 48) - 1
        ):
            raise ValueError()
        import pwd

        account = pwd.getpwnam("aethron")
        if account.pw_uid <= 0 or account.pw_gid <= 0:
            raise ValueError()
        result = subprocess.run(
            [
                "/opt/aethron/venv/bin/python",
                "-I",
                "-B",
                "-m",
                "aethron_edge",
                "initialize-telemetry",
                "--config",
                "/opt/aethron/appliance.json",
                "--name",
                name,
                "--replay-floor",
                str(timestamp_floor),
            ],
            user=account.pw_uid,
            group=account.pw_gid,
            extra_groups=[],
            umask=0o077,
            cwd="/",
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise ValueError()
        return {"journal_created": True, "policy_bound": True, "authority_issued": False}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        # A timeout/failure may follow publication; never delete or retry state.
        raise ValueError("service_telemetry_provisioning_failed") from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--trust-root", type=Path)
    parser.add_argument("--initialize-telemetry", metavar="NAME")
    parser.add_argument("--replay-floor", type=int)
    args = parser.parse_args()
    if args.initialize_telemetry is not None:
        if any(value is not None for value in (args.root, args.bundle, args.trust_root)):
            parser.error("provisioning uses fixed installed paths; install arguments forbidden")
        try:
            print(json.dumps(provision_telemetry(args.initialize_telemetry, args.replay_floor)))
        except ValueError:
            parser.exit(2, "service_telemetry_provisioning_failed\n")
    else:
        if args.replay_floor is not None or any(
            value is None for value in (args.root, args.bundle, args.trust_root)
        ):
            parser.error("installation requires --root, --bundle, --trust-root only")
        print(install(args.root, args.bundle, args.trust_root))
