"""Deterministic source and executable artifacts, SBOM and unsigned local provenance."""

import gzip
import hashlib
import io
import json
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(destination):
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    names = sorted(n for n in names if n)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=ROOT
    )
    if dirty:
        raise SystemExit("release requires clean committed source")
    blobs = {n: (ROOT / n).read_bytes() for n in names}
    manifest = {n: hashlib.sha256(data).hexdigest() for n, data in blobs.items()}
    out = Path(destination)
    out.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, data in blobs.items():
            info = tarfile.TarInfo("aethron-0.2.0/" + name)
            info.size = len(data)
            info.mode = 0o644
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))
    (out / "aethron-0.2.0-source.tar.gz").write_bytes(gzip.compress(buffer.getvalue(), mtime=0))
    with zipfile.ZipFile(out / "aethron.pyz", "w", compression=zipfile.ZIP_STORED) as archive:
        app = {n: data for n, data in blobs.items() if n.startswith("aethron/")}
        app["__main__.py"] = b"from aethron.__main__ import main\nraise SystemExit(main())\n"
        app["LICENSE"] = blobs["LICENSE"]
        app["NOTICE"] = blobs["NOTICE"]
        for name, data in sorted(app.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    (out / "source-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "aethron",
                "version": "0.2.0",
                "licenses": [{"license": {"id": "Apache-2.0"}}],
            }
        },
        "components": [
            {
                "type": "data",
                "name": "Amazon AOT derived25-frame evaluation excerpt",
                "version": "2026-10-08",
                "licenses": [{"license": {"id": "CDLA-Permissive-1.0"}}],
            },
            {
                "type": "data",
                "name": "NASA public-domain and CC0 RGB smoke photographs",
                "version": "scikit-image-v0.25.2",
                "licenses": [
                    {"license": {"name": "Public domain / CC0-1.0; see data/rgb-smoke/README.md"}}
                ],
            },
            {
                "type": "library",
                "name": "Python standard library",
                "version": "runtime-provided",
                "licenses": [{"license": {"id": "Python-2.0"}}],
            },
        ],
        "dependencies": [],
        "properties": [
            {
                "name": "aethron:optional-vision",
                "value": "numpy2.3.5;opencv-python-headless4.13.0.92; separately installed, not in zipapp",
            },
            {
                "name": "aethron:optional-coreml",
                "value": "onnxruntime1.30.0;flatbuffers25.12.19;protobuf7.36.2; separate macOS Apple Silicon opt-in, not bundled",
            },
            {
                "name": "aethron:optional-model-sha256",
                "value": "c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063",
            },
        ],
    }
    (out / "sbom.cdx.json").write_text(
        json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    provenance = {
        "source_revision": revision,
        "source_manifest_sha256": hashlib.sha256(
            (out / "source-manifest.json").read_bytes()
        ).hexdigest(),
        "builder": "scripts/release.py",
        "evidence": "local unsigned candidate; not hosted attestation",
        "runtime_dependencies": "Python 3.9+ standard library",
        "model_sha256": manifest["aethron/models/rules.json"],
        "data_manifests": {n: h for n, h in manifest.items() if n.endswith("freeze.json")},
    }
    (out / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksums = "".join(
        hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n"
        for p in sorted(out.iterdir())
        if p.is_file() and p.name != "SHA256SUMS"
    )
    (out / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    return revision


if __name__ == "__main__":
    import sys

    print(build(sys.argv[1] if len(sys.argv) > 1 else "dist"))
