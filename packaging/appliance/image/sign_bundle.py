"""Build-only signing: the BuildKit secret is never copied into a layer."""

import hashlib
import json
import shutil
import stat
import subprocess
from pathlib import Path


def sign(path, version):
    if path.is_symlink():
        raise ValueError("unsupported_bundle_entry")
    files = {}
    for entry in sorted(path.rglob("*")):
        mode = entry.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError("unsupported_bundle_entry")
        name = str(entry.relative_to(path))
        if name not in ("manifest.json", "manifest.sig"):
            files[name] = hashlib.sha256(entry.read_bytes()).hexdigest()
    (path / "manifest.json").write_text(
        json.dumps(
            {"schema_version": 1, "config_version": 1, "version": version, "files": files},
            sort_keys=True,
        )
    )
    subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-sign",
            "-rawin",
            "-inkey",
            "/run/secrets/testkey",
            "-in",
            str(path / "manifest.json"),
            "-out",
            str(path / "manifest.sig"),
        ],
        check=True,
    )


def normalize_venv_alias(initial):
    # CPython's POSIX venv adds this redundant directory link. It is not a
    # signed file, and copytree would otherwise duplicate the entire library.
    if initial.is_symlink() or (initial / "venv").is_symlink():
        raise ValueError("unexpected_venv_alias")
    alias = initial / "venv" / "lib64"
    if alias.is_symlink():
        if alias.readlink() != Path("lib"):
            raise ValueError("unexpected_venv_alias")
        library = alias.parent / "lib"
        if library.is_symlink() or not library.is_dir():
            raise ValueError("unexpected_venv_alias")
        alias.unlink()


def main():
    initial = Path("/opt/aethron")
    normalize_venv_alias(initial)
    sign(initial, 1)
    candidate = Path("/opt/aethron-update-candidate")
    shutil.copytree(initial, candidate)
    config = json.loads((candidate / "appliance.json").read_text())
    config["profiles"][0]["contract"] = "vehicle_stop"  # recommendation only, never actuation
    (candidate / "appliance.json").write_text(json.dumps(config))
    sign(candidate, 2)
    subprocess.run(
        [
            "openssl",
            "pkey",
            "-in",
            "/run/secrets/testkey",
            "-pubout",
            "-out",
            "/etc/aethron/trust.pub",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
