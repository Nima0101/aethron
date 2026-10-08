"""Explicit development-only fetch. Runtime has no downloader or arbitrary model loading."""

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aethron.vision.yolox import MODEL_BYTES, MODEL_SHA256  # noqa: E402

URL = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/object_detection_yolox/object_detection_yolox_2022nov.onnx"


def run():
    out = ROOT / "build/models/yolox.onnx"
    if out.exists() and hashlib.sha256(out.read_bytes()).hexdigest() == MODEL_SHA256:
        print("Pinned RGB model already verified")
        return
    with urllib.request.urlopen(URL, timeout=60) as response:
        blob = response.read(MODEL_BYTES + 1)
    assert len(blob) == MODEL_BYTES and hashlib.sha256(blob).hexdigest() == MODEL_SHA256
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    print("Downloaded pinned Apache-2.0 OpenCV Zoo YOLOX model; no field qualification")


if __name__ == "__main__":
    run()
