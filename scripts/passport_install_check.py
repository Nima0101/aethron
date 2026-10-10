"""Check P16 installed-source identity; developer tooling, not artifact authentication."""

import importlib
import json
import sys
from hashlib import sha256
from pathlib import Path

MODULES = (
    "aethron.passports",
    "aethron.passport_evidence",
    "aethron.interop_tasks",
    "aethron.interop_bundles",
    "aethron.interop_federation",
    "aethron.interop_inbox",
    "aethron._json_bounds",
)


def check_file(source, installed, source_root):
    """Require an external installed copy with the same bytes as reviewed source."""
    installed = installed.resolve(strict=True)
    source_root = source_root.resolve(strict=True)
    if installed == source_root or source_root in installed.parents:
        raise ValueError("source_tree_import")
    source_bytes = source.read_bytes()
    if installed.read_bytes() != source_bytes:
        raise ValueError("installed_source_mismatch")
    return sha256(source_bytes).hexdigest()


if __name__ == "__main__":
    if not sys.flags.isolated:
        raise SystemExit("run with python -I")
    root = Path(__file__).resolve().parents[1]
    checked = {}
    for name in MODULES:
        module = importlib.import_module(name)
        relative = Path(*name.split(".")).with_suffix(".py")
        checked[str(relative)] = check_file(root / relative, Path(module.__file__), root)
    print(json.dumps({"installed_source_sha256": checked}, sort_keys=True))
