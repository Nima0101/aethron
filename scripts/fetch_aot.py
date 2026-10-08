"""Reproduce the licensed excerpt from hash-pinned original recordings, never label-selected crops."""

import hashlib
import io
import json
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://airborne-obj-detection-challenge-training.s3.amazonaws.com/part1/Images/"


def run():
    manifest = json.loads((ROOT / "data/aot/manifest.json").read_text())
    out = ROOT / "build/aot-reproduced"
    out.mkdir(parents=True, exist_ok=True)
    for item in manifest["frames"]:
        assert item["url"].startswith(BASE)
        with urllib.request.urlopen(item["url"], timeout=60) as response:
            blob = response.read(10000001)
        assert len(blob) <= 10000000 and hashlib.sha256(blob).hexdigest() == item["source_sha256"]
        im = Image.open(io.BytesIO(blob)).convert("L").resize((612, 512), Image.Resampling.BOX)
        data = b"P5\n612 512\n255\n" + im.tobytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"]
        assert data == (ROOT / "data/aot" / item["file"]).read_bytes()
        (out / item["file"]).write_bytes(data)
    print(
        "PASS:25 licensed original camera frames fetched, hashed, transformed and byte-reproduced"
    )


if __name__ == "__main__":
    run()
