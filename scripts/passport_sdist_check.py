"""Inspect selected inputs in a locally built sdist; never extract or execute members.

This developer check is not an untrusted-archive validator or artifact authentication.
The CLI requires Python 3.11+ for project metadata; hosted execution uses 3.13.
"""

import argparse
import json
import tarfile
from hashlib import sha256
from pathlib import Path


def required_inputs(root):
    """The finite published consumer inventory, not dependency closure."""
    required = {
        "examples/passports/README.md",
        "requirements-passport-sensor-conformance.txt",
        "requirements-passport-conformance.txt",
        "requirements-passports.txt",
        "tests/test_passport_schemas.py",
        "tests/test_passport_floor_store.py",
        "aethron/passport_floor_store.py",
        "tests/interop_consumers/test_sensor_packets.py",
        "tests/interop_consumers/test_ros_status.py",
    }
    for name in ("edge-unknown", "sensor-packet", "sensor-encoding", "ros-status"):
        path = f"examples/interop/{name}-vectors-v1.json"
        required.add(path)
        required.update(json.loads((root / path).read_bytes())["source_sha256"])
    return required


def check_archive(path, prefix, expected):
    """Compare exact regular members with trusted checkout bytes, without extraction."""
    names = {f"{prefix}/{name}": name for name in expected}
    checked = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            relative = names.get(member.name)
            if relative is None:
                continue
            if relative in checked:
                raise ValueError("duplicate_archive_input")
            if not member.isreg() or member.sparse is not None:
                raise ValueError("invalid_archive_input_type")
            source = expected[relative]
            if member.size != len(source):
                raise ValueError("archive_input_mismatch")
            with archive.extractfile(member) as stream:
                if stream.read(len(source) + 1) != source:
                    raise ValueError("archive_input_mismatch")
            checked[relative] = sha256(source).hexdigest()
    if set(checked) != set(expected):
        raise ValueError("missing_archive_input")
    return checked


if __name__ == "__main__":
    import tomllib

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    # This repository uses a static, already normalized distribution name/version.
    prefix = f"{project['name']}-{project['version']}"
    expected = {name: (root / name).read_bytes() for name in sorted(required_inputs(root))}
    checked = check_archive(args.archive, prefix, expected)
    print(json.dumps({"selected_source_sha256": checked}, sort_keys=True))
