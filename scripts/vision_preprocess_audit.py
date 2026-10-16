"""Bounded preprocessing comparison with a caller-supplied local C probe library."""

import argparse
import ctypes
import hashlib
import json
import platform
import statistics
import time
from pathlib import Path

import cv2 as cv
import numpy as np
from aethron_vision_native import PACK_CONTRACT_VERSION

from aethron.vision.yolox import _packed_rgb


def prepare(rgb, method, pack):
    height, width = rgb.shape[:2]
    scale = min(640 / width, 640 / height)
    resized = cv.resize(
        rgb, (int(width * scale), int(height * scale)), interpolation=cv.INTER_LINEAR
    )
    canvas = np.full((640, 640, 3), 114, dtype=np.uint8)
    canvas[: resized.shape[0], : resized.shape[1]] = resized
    if method == "numpy":
        return np.ascontiguousarray(canvas.transpose(2, 0, 1)[None], dtype=np.float32)
    if method == "selected":
        return _packed_rgb(canvas)
    if method == "opencv_blob":
        return cv.dnn.blobFromImage(
            canvas,
            scalefactor=1.0,
            size=(640, 640),
            mean=(0, 0, 0),
            swapRB=False,
            crop=False,
            ddepth=cv.CV_32F,
        )
    if method != "c_pack":
        raise ValueError("invalid_probe_method")
    output = np.empty((1, 3, 640, 640), dtype=np.float32)
    # Both buffers originate here, have fixed size, are disjoint and contiguous,
    # and remain owned for the synchronous call. The prototype retains neither.
    pack(canvas.ctypes.data, output.ctypes.data)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--probe", type=Path, required=True, help="locally compiled tests/probes/vision_pack.c"
    )
    args = parser.parse_args()
    if PACK_CONTRACT_VERSION != 1:
        raise RuntimeError("packing_contract_mismatch")
    library = ctypes.CDLL(str(args.probe.resolve()))
    pack = library.pack
    pack.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    pack.restype = None
    cv.setNumThreads(1)
    rng = np.random.default_rng(20261010)
    root = Path(__file__).resolve().parents[1]
    report = {
        "audit_policy_version": 2,
        "qualified": False,
        "scope": "full RGB preprocessing only; no model inference or hardware qualification",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "opencv": cv.__version__,
        "probe_sha256": hashlib.sha256(args.probe.read_bytes()).hexdigest(),
        "source_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in (
                "aethron/vision/yolox.py",
                "tests/probes/vision_pack.c",
                "scripts/vision_preprocess_audit.py",
                "tests/test_vision_preprocess.py",
                "integrations/native-vision/aethron_vision_native/bounds.c",
            )
        },
        "cases": {},
        "timed_parity_checks": 0,
        "order": "alternate method order per repetition; retain every wall/CPU sample",
    }
    for height, width in ((1, 1), (359, 641), (720, 1280)):
        rgb = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
        reference = prepare(rgb, "numpy", pack)
        samples = {
            key: {"wall_ns": [], "cpu_ns": []}
            for key in ("numpy", "opencv_blob", "c_pack", "selected")
        }
        for method in samples:
            np.testing.assert_array_equal(reference, prepare(rgb, method, pack))
        for iteration in range(5):
            for method in list(samples)[:: 1 if iteration % 2 else -1]:
                start, cpu = time.perf_counter_ns(), time.process_time_ns()
                output = prepare(rgb, method, pack)
                samples[method]["cpu_ns"].append(time.process_time_ns() - cpu)
                samples[method]["wall_ns"].append(time.perf_counter_ns() - start)
                np.testing.assert_array_equal(reference, output)
                report["timed_parity_checks"] += 1
        for values in samples.values():
            values["wall_median_ns"] = int(statistics.median(values["wall_ns"]))
            values["cpu_median_ns"] = int(statistics.median(values["cpu_ns"]))
        report["cases"][f"{height}x{width}"] = samples
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
