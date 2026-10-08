"""Offline root-directory installer; never starts a service on the build Mac."""

import argparse
import shutil
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--trust-root", type=Path, required=True)
    args = parser.parse_args()
    print(install(args.root, args.bundle, args.trust_root))
