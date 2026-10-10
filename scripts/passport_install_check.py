"""Check P16 installed-source identity; developer tooling, not artifact authentication."""

import importlib
import json
import sys
from base64 import urlsafe_b64encode
from hashlib import sha256
from importlib.metadata import distribution
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


def check_record(distribution, relative, installed, source_bytes):
    """Associate a selected imported file with local distribution metadata.

    RECORD is not a publisher signature. This deliberately requires SHA-256 and
    size for these source members of our regular wheel installation.
    """
    files = distribution.files
    if files is None:
        raise ValueError("missing_distribution_record")
    entries = [entry for entry in files if entry.as_posix() == relative]
    if len(entries) != 1:
        raise ValueError("invalid_distribution_member")
    entry = entries[0]
    if Path(distribution.locate_file(entry)).resolve(strict=True) != installed.resolve(strict=True):
        raise ValueError("distribution_location_mismatch")
    expected = urlsafe_b64encode(sha256(source_bytes).digest()).decode("ascii").rstrip("=")
    if entry.hash is None or entry.hash.mode != "sha256" or entry.hash.value != expected:
        raise ValueError("distribution_hash_mismatch")
    if entry.size != len(source_bytes):
        raise ValueError("distribution_size_mismatch")


if __name__ == "__main__":
    if not sys.flags.isolated:
        raise SystemExit("run with python -I")
    root = Path(__file__).resolve().parents[1]
    installed_distribution = distribution("aethron")
    checked = {}
    for name in MODULES:
        module = importlib.import_module(name)
        relative = Path(*name.split(".")).with_suffix(".py")
        checked[str(relative)] = check_file(root / relative, Path(module.__file__), root)
        check_record(
            installed_distribution,
            relative.as_posix(),
            Path(module.__file__),
            (root / relative).read_bytes(),
        )
    print(json.dumps({"installed_source_sha256": checked}, sort_keys=True))
