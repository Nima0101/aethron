"""Fixed CPU-thread profile experiment in this process only; no model/threshold tuning."""

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
from aethron.vision.yolox import RGBDetector  # noqa: E402


def run():
    image = np.array(Image.open(ROOT / "data/rgb-smoke/person.png").convert("RGB"))
    reports = []
    reference = None
    # Declared before execution:1/2/4 threads,2 warmup +5 timed same-image calls each.
    for count in (1, 2, 4):
        cv2.setNumThreads(count)
        model = RGBDetector(ROOT / "build/models/yolox.onnx")
        for _ in range(2):
            model.infer(image, lighting="daylight")
        timings = []
        cpu = []
        for _ in range(5):
            start = time.perf_counter()
            started_cpu = time.process_time()
            ds = model.infer(image, lighting="daylight")
            timings.append((time.perf_counter() - start) * 1000)
            cpu.append((time.process_time() - started_cpu) * 1000)
            if reference is None:
                reference = ds
            assert ds == reference, "Thread setting changed deterministic detections"
        reports.append(
            {
                "threads": count,
                "samples": 5,
                "median_wall_ms": statistics.median(timings),
                "max_wall_ms": max(timings),
                "median_cpu_ms": statistics.median(cpu),
                "detections_identical": True,
            }
        )
    result = {
        "experiment": "fixed1/2/4 thread comparison; same pinned model and photograph;2 warmup+5 samples",
        "platform": platform.system() + " " + platform.machine(),
        "python": platform.python_version(),
        "opencv": cv2.__version__,
        "results": reports,
        "qualification": "Small CPU integration experiment; not a deployment deadline or sensor proof.",
    }
    (ROOT / "build/vision/thread-profile.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    run()
