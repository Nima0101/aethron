"""Compare pinned YOLOX pixel outputs and end-to-end inference on macOS Core ML.

This is an acceleration regression experiment, never a field/UAV qualification.
"""

import json
import platform
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rescuesense.temporal.math import iou  # noqa: E402
from rescuesense.temporal.pixels import decode_pgm  # noqa: E402
from rescuesense.vision.yolox import MODEL_SHA256, RGBDetector  # noqa: E402


def p95(values):
    return sorted(values)[int(0.95 * len(values)) - 1]


def sample_pixels():
    for name in ("person", "animal"):
        image = Image.open(ROOT / "data/rgb-smoke" / f"{name}.png").convert("RGB")
        yield name, np.asarray(image)
    manifest = json.loads((ROOT / "data/aot/manifest.json").read_text())
    for entry in manifest["frames"]:
        w, h, pixels = decode_pgm((ROOT / "data/aot" / entry["file"]).read_bytes())
        gray = np.frombuffer(pixels, dtype=np.uint8).reshape(h, w)
        yield entry["file"], np.repeat(gray[:, :, None], 3, axis=2)


def matches(a, b):
    if len(a) != len(b):
        return False
    return all(
        x["class"] == y["class"]
        and iou(x["box"], y["box"]) >= 0.98
        and abs(x["score"] - y["score"]) <= 0.005
        for x, y in zip(a, b)
    )


def run():
    cv2.setNumThreads(2)
    path = ROOT / "build/models/yolox.onnx"
    baseline = RGBDetector(path, backend="opencv")
    start = time.perf_counter()
    accelerated = RGBDetector(path, backend="coreml")
    load_ms = round((time.perf_counter() - start) * 1000, 3)
    first = np.asarray(Image.open(ROOT / "data/rgb-smoke/person.png").convert("RGB"))
    cold_start = time.perf_counter()
    accelerated.infer(first, lighting="daylight")
    first_inference_ms = round((time.perf_counter() - cold_start) * 1000, 3)
    accelerated.infer(first, lighting="daylight")
    cpu_ms, coreml_ms, mismatches = [], [], []
    names = []
    for name, pixels in sample_pixels():
        t = time.perf_counter()
        cpu = baseline.infer(pixels, lighting="daylight")
        cpu_ms.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        coreml = accelerated.infer(pixels, lighting="daylight")
        coreml_ms.append((time.perf_counter() - t) * 1000)
        names.append(name)
        if not matches(cpu, coreml):
            mismatches.append({"sample": name, "cpu": cpu, "coreml": coreml})
    negative = np.zeros((128, 128, 3), dtype=np.uint8)
    dark_suppression = accelerated.infer(first, lighting="zero_visible") == []
    empty_negative = accelerated.infer(negative, lighting="daylight") == []
    report = {
        "model_sha256": MODEL_SHA256,
        "runtime": f"{platform.system()} {platform.machine()} Python {platform.python_version()}",
        "samples": len(names),
        "coreml_provider_required": True,
        "model_load_ms": load_ms,
        "first_inference_ms": first_inference_ms,
        "opencv_p50_ms": round(statistics.median(cpu_ms), 3),
        "opencv_p95_ms": round(p95(cpu_ms), 3),
        "coreml_p50_ms": round(statistics.median(coreml_ms), 3),
        "coreml_p95_ms": round(p95(coreml_ms), 3),
        "coreml_max_ms": round(max(coreml_ms), 3),
        "coreml_within_100ms_on_sample": p95(coreml_ms) <= 100,
        "output_equivalence_passed": not mismatches,
        "mismatches": mismatches,
        "darkness_suppressed": dark_suppression,
        "empty_negative": empty_negative,
        "qualification": "Recorded/still pixel integration only; no sensor, UAV or deployment proof.",
    }
    dest = ROOT / "build/coreml-comparison.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    assert not mismatches, "CPU/Core ML output discrepancy; see retained report"
    assert dark_suppression and empty_negative
    return report


if __name__ == "__main__":
    run()
