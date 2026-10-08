"""Build-only signing: the BuildKit secret is never copied into a layer."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def sign(path, version):
    files = {
        str(f.relative_to(path)): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(path.rglob("*"))
        if f.is_file() and str(f.relative_to(path)) not in ("manifest.json", "manifest.sig")
    }
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


initial = Path("/opt/aethron")
sign(initial, 1)
candidate = Path("/opt/aethron-update-candidate")
shutil.copytree(initial, candidate)
config = json.loads((candidate / "appliance.json").read_text())
config["profiles"][0]["contract"] = "vehicle_stop"  # recommendation only, never actuation
(candidate / "appliance.json").write_text(json.dumps(config))
sign(candidate, 2)
subprocess.run(
    ["openssl", "pkey", "-in", "/run/secrets/testkey", "-pubout", "-out", "/etc/aethron/trust.pub"],
    check=True,
)
