"""Separate optional-dependency/model inventory, without leaking installation paths."""

import hashlib
import importlib.metadata
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
components = []
for name in ("numpy", "opencv-python-headless", "onnxruntime", "flatbuffers", "protobuf"):
    try:
        dist = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        if name in ("numpy", "opencv-python-headless"):
            raise
        continue  # Core ML is an optional, separately installed dependency.
    licenses = {}
    for entry in dist.files or []:
        if "license" in str(entry).lower() and Path(dist.locate_file(entry)).is_file():
            licenses[str(entry)] = hashlib.sha256(
                Path(dist.locate_file(entry)).read_bytes()
            ).hexdigest()
    components.append(
        {"type": "library", "name": name, "version": dist.version, "license_files_sha256": licenses}
    )
model = ROOT / "build/models/yolox.onnx"
report = {
    "scope": "optional vision, excluded from core zipapp",
    "components": components,
    "model": {
        "name": "OpenCV Zoo YOLOX-S",
        "bytes": model.stat().st_size,
        "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "license": "Apache-2.0",
    },
    "runtime_loader": "Exact model hash verified before native ONNX parsing",
}
out = ROOT / "build/vision"
out.mkdir(parents=True, exist_ok=True)
(out / "supply-chain.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
