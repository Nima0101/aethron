"""Actual pinned learned model -> schema -> temporal replay on licensed recorded pixels."""

import io
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from temporal_evaluate import metrics  # noqa: E402

from aethron.temporal.fixtures import encode, frame  # noqa: E402
from aethron.temporal.pixels import decode_pgm  # noqa: E402
from aethron.temporal.registration import estimate_translation  # noqa: E402
from aethron.temporal.replay import replay  # noqa: E402
from aethron.vision.yolox import MODEL_SHA256, RGBDetector  # noqa: E402


def run():
    backend = os.environ.get("AETHRON_VISION_BACKEND", "opencv")
    start_load = time.perf_counter()
    detector = RGBDetector(ROOT / "build/models/yolox.onnx", backend=backend)
    model_load_ms = round((time.perf_counter() - start_load) * 1000, 3)
    empty = np.zeros((128, 128, 3), dtype=np.uint8)
    first_start = time.perf_counter()
    assert detector.infer(empty, lighting="daylight") == []
    first_inference_ms = round((time.perf_counter() - first_start) * 1000, 3)
    assert detector.infer(empty, lighting="zero_visible") == []
    manifest = json.loads((ROOT / "data/aot/manifest.json").read_text())
    entries = []
    previous = None
    latencies = []
    starts = {}
    registration = 0
    for item in manifest["frames"]:
        data = (ROOT / "data/aot" / item["file"]).read_bytes()
        w, h, pixels = decode_pgm(data)
        rgb = np.repeat(np.frombuffer(pixels, dtype=np.uint8).reshape(h, w, 1), 3, axis=2)
        start = time.perf_counter()
        ds = detector.infer(rgb, lighting="daylight")
        latencies.append(round((time.perf_counter() - start) * 1000, 3))
        assert ds == detector.infer(rgb, lighting="daylight"), "model nondeterminism"
        seq = item["sequence"]
        starts.setdefault(seq, item["time_ns"])
        at = (item["time_ns"] - starts[seq]) // 1000000 + (5000 if seq == "negative" else 0)
        f = frame(at, ds, kind="rgb")
        f["evidence"] = "recorded"
        f["scene_break"] = not entries or seq != manifest["frames"][len(entries) - 1]["sequence"]
        f["ego"] = (
            estimate_translation(previous, data)
            if previous and not f["scene_break"]
            else {"dx": 0.0, "dy": 0.0, "variance": 0.05, "valid": False}
        )
        registration += int(f["ego"]["valid"])
        previous = data
        entries.append({"frame": f, "truth": item["truth"]})
    raw = b"\n".join(encode(e["frame"]) for e in entries) + b"\n"
    results = list(replay(io.BytesIO(raw)))
    report = {
        "model_sha256": MODEL_SHA256,
        "backend": backend,
        "frames": len(entries),
        "metrics": metrics(entries, results),
        "inference_ms": latencies,
        "model_load_ms": model_load_ms,
        "first_inference_ms": first_inference_ms,
        "recorded_latency_ms": {
            "p50": round(statistics.median(latencies), 3),
            "p95": sorted(latencies)[math.ceil(0.95 * len(latencies)) - 1],
            "max": max(latencies),
            "all_frames_under_100_ms": all(t <= 100 for t in latencies),
            "scope": "Warm model inference and preprocessing/postprocessing, not camera or controller",
        },
        "deterministic_duplicate_inference": True,
        "empty_negative": True,
        "zero_light_suppressed": True,
        "valid_registration_frames": registration,
        "qualification": "Offline integration/regression only. No thermal/UAV or live qualification.",
    }
    out = ROOT / ("build/vision-coreml" if backend == "coreml" else "build/vision")
    out.mkdir(parents=True, exist_ok=True)
    (out / "input.jsonl").write_bytes(raw)
    (out / "output.json").write_text(json.dumps(results, indent=2) + "\n")
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    run()
