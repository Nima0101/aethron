"""Verify exact bundled TensorFlow.js COCO-SSD Lite weights before web publishing."""

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "web/public/models/coco-ssd-lite"
SHA256 = {
    "model.json": "3770b2528339b1e3340cb74360e1e40401816b009779aeb8d0cce3a4353ea3a9",
    "group1-shard1of5": "0e7af0f713e98521252321f7f84892c31cefccccec3ac64c84e5065b75ed5646",
    "group1-shard2of5": "74cc6cfc2c4510c9cd81b8ad4cebf6f6a8f305119bb365ce0eb96276da38519a",
    "group1-shard3of5": "50383033f893eae136392a403e8f70ade5efd90867df5695c4ca5ac640e14f38",
    "group1-shard4of5": "d856dc534c780068bbf6c666ce1516df2c8433d87578aa31fcdf197de7058cc2",
    "group1-shard5of5": "3d356f1fb6dfca6af78c56db34d9326706d0196e303f9de6b04f236ca79ed309",
}


def run():
    for name, digest in SHA256.items():
        path = MODEL / name
        assert path.is_file(), f"Missing browser model: {name}"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == digest, f"Browser model checksum mismatch: {name}"
    print(f"PASS: {len(SHA256)} pinned, same-origin browser model files")


if __name__ == "__main__":
    try:
        run()
    except (AssertionError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
