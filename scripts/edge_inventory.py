"""Reproducible runtime inventory from the actual wheel lock closure."""

import email
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run():
    names = {"aethron": "0.2.0", "aethron-edge": "0.1.0"}
    for lock in ("requirements-server.lock", "requirements-vision.lock"):
        for name, version in re.findall(
            r"^([a-zA-Z0-9_-]+)==([^\s]+)", (ROOT / "integrations/edge" / lock).read_text(), re.M
        ):
            names[name] = version
    metadata = {}
    wheels = list((ROOT / "build/ecosystem-phase1/wheelhouse").glob("*.whl"))
    wheels += list((ROOT / "build/ecosystem-phase1/package/a").glob("*.whl"))
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as archive:
            entry = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
            value = email.message_from_bytes(archive.read(entry))
            metadata[value["Name"].lower().replace("_", "-")] = (value, wheel)
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
    output = ROOT / "build/ecosystem-phase1/edge-sbom.json"
    output.write_text(json.dumps(bom, indent=2, sort_keys=True) + "\n")
    print(f"Inventoried {len(components)} runtime components; no hardware qualification")


if __name__ == "__main__":
    run()
