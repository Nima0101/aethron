"""Reproducible runtime inventory from the actual wheel lock closure."""

import email
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def wheel_components(candidate: Path, dependencies: Path, names):
    normalized = {}
    for name, version in names.items():
        key = re.sub(r"[-_.]+", "-", name.lower())
        if key in normalized and normalized[key] != version:
            raise ValueError("conflicting_expected_versions")
        normalized[key] = version
    names = normalized
    metadata = {}
    owned = {"aethron", "aethron-edge"}
    for folder, project_owned in ((candidate, True), (dependencies, False)):
        for wheel in sorted(folder.glob("*.whl")):
            with zipfile.ZipFile(wheel) as archive:
                entries = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
                if len(entries) != 1:
                    raise ValueError("ambiguous_wheel_metadata")
                value = email.message_from_bytes(archive.read(entries[0]))
            if len(value.get_all("Name", [])) != 1 or len(value.get_all("Version", [])) != 1:
                raise ValueError("ambiguous_distribution_identity")
            name = re.sub(r"[-_.]+", "-", value["Name"].lower())
            if name not in names or (name in owned) != project_owned:
                continue
            if name in metadata:
                raise ValueError("ambiguous_wheel_candidate: " + name)
            metadata[name] = (value, wheel)
    if set(metadata) != set(names):
        raise ValueError("missing_expected_wheel")
    components = []
    for name, version in sorted(names.items()):
        distribution, wheel = metadata[name.lower().replace("_", "-")]
        if distribution["Version"] != version:
            raise ValueError("installed_version_differs_from_lock: " + name)
        expression = distribution.get("License-Expression")
        license_name = distribution.get("License")
        licenses = (
            [{"expression": expression}]
            if expression
            else [{"license": {"name": license_name}}]
            if license_name
            else []
        )
        component = {
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:pypi/{name}@{version}",
            "bom-ref": f"pkg:pypi/{name}@{version}",
            "hashes": [
                {"alg": "SHA-256", "content": hashlib.sha256(wheel.read_bytes()).hexdigest()}
            ],
        }
        if licenses:
            component["licenses"] = licenses
        components.append(component)
    return components


def run(candidate: Path, dependencies: Path, output: Path):
    names = {"aethron": "0.2.0", "aethron-edge": "0.1.0"}
    for lock in ("requirements-server.lock", "requirements-vision.lock"):
        for name, version in re.findall(
            r"^([a-zA-Z0-9_-]+)==([^\s]+)", (ROOT / "integrations/edge" / lock).read_text(), re.M
        ):
            names[name] = version
    components = wheel_components(candidate, dependencies, names)
    model = ROOT / "build/models/yolox.onnx"
    components.append(
        {
            "type": "machine-learning-model",
            "name": "OpenCV Zoo YOLOX-S",
            "version": "2022nov",
            "bom-ref": "aethron:frozen-yolox",
            "hashes": [
                {"alg": "SHA-256", "content": hashlib.sha256(model.read_bytes()).hexdigest()}
            ],
            "licenses": [{"expression": "Apache-2.0"}],
        }
    )
    bom = {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1, "components": components}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(bom, indent=2, sort_keys=True) + "\n")
    print(f"Inventoried {len(components)} runtime components; no hardware qualification")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheels", type=Path, default=ROOT / "build/ecosystem-phase1/package/a")
    parser.add_argument(
        "--wheelhouse", type=Path, default=ROOT / "build/ecosystem-phase1/wheelhouse"
    )
    parser.add_argument("--out", type=Path, default=ROOT / "build/ecosystem-phase1/edge-sbom.json")
    args = parser.parse_args()
    run(args.wheels, args.wheelhouse, args.out)
