"""Compare native CPU engines through the frozen YOLOX pre/postprocessing."""

import argparse
import copy
import hashlib
import json
import statistics
import time
from pathlib import Path

from aethron.temporal.math import iou
from aethron.vision.yolox import MODEL_BYTES, MODEL_SHA256, RGBDetector


def run(model, images):
    import cv2
    import numpy as np
    import onnxruntime as ort

    cv2.setNumThreads(2)
    baseline = RGBDetector(model)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    with Path(model).open("rb") as stream:
        blob = stream.read(MODEL_BYTES + 1)
    if len(blob) != MODEL_BYTES or hashlib.sha256(blob).hexdigest() != MODEL_SHA256:
        raise ValueError("Untrusted model bytes")
    session = ort.InferenceSession(blob, sess_options=options, providers=["CPUExecutionProvider"])
    session.disable_fallback()
    name = session.get_inputs()[0].name

    class NativeCPU:
        # Probe adapter only: share the exact product preprocessing and output
        # admission, while substituting the native forward operation.
        def setInput(self, tensor):
            self.tensor = tensor

        def forward(self):
            return session.run(None, {name: self.tensor})[0]

    candidate = copy.copy(baseline)
    candidate.net = NativeCPU()
    samples = [(p.name, cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)) for p in images]
    samples.append(("empty", np.zeros((128, 128, 3), dtype=np.uint8)))
    elapsed = {"opencv": [], "ort_cpu": []}
    comparisons = []
    for label, pixels in samples:
        outputs = {}
        for backend, detector in (("opencv", baseline), ("ort_cpu", candidate)):
            detector.infer(pixels, lighting="daylight")
            for _ in range(3):
                started = time.perf_counter_ns()
                result = detector.infer(pixels, lighting="daylight")
                elapsed[backend].append(time.perf_counter_ns() - started)
            outputs[backend] = result
            if detector.infer(pixels, lighting="zero_visible") != []:
                raise RuntimeError("Darkness suppression failed")
        a, b = outputs.values()
        # Existing Core ML comparison bounds, unchanged: identical order/class,
        # IoU >= .98, score difference <= .005. Exact equality reported separately.
        parity = len(a) == len(b) and all(
            x["class"] == y["class"]
            and iou(x["box"], y["box"]) >= 0.98
            and abs(x["score"] - y["score"]) <= 0.005
            for x, y in zip(a, b)
        )
        comparisons.append(
            {
                "sample": label,
                "pixels_sha256": hashlib.sha256(pixels.tobytes()).hexdigest(),
                "detections": [len(a), len(b)],
                "exact": a == b,
                "existing_parity": parity,
            }
        )
    return {
        "model_sha256": MODEL_SHA256,
        "runtimes": {"opencv": cv2.__version__, "ort_cpu": ort.__version__},
        "threads": 2,
        "samples": comparisons,
        "median_ns": {k: int(statistics.median(v)) for k, v in elapsed.items()},
        "latencies_ns": elapsed,
        "qualified": False,
        "scope": "bounded still-image CPU comparison; no device or field qualification",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--images", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.model, args.images), sort_keys=True))
