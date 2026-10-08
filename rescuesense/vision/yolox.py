"""Pinned OpenCV Zoo RGB detector. No identity features, history or arbitrary-model loader."""

import hashlib
from pathlib import Path

from ..schema import enum, require

MODEL_SHA256 = "c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063"
MODEL_BYTES = 35858002


def safe_class(index):
    if index == 0:
        return "person"
    if index in (2, 3, 5, 6, 7, 8):
        return "vehicle"
    if 14 <= index <= 23:
        return "animal"
    if index == 1:
        return "equipment"
    if index in (4, 9, 10, 11, 12, 13):
        return "obstacle"
    return None


class RGBDetector:
    def __init__(self, model_path, *, backend="opencv"):
        # Validate in Python before handing trusted bytes to any native ONNX parser.
        with Path(model_path).open("rb") as stream:
            blob = stream.read(MODEL_BYTES + 1)
        require(len(blob) == MODEL_BYTES and hashlib.sha256(blob).hexdigest() == MODEL_SHA256)
        require(backend in ("opencv", "coreml"))
        import cv2
        import numpy as np

        self.cv, self.np = cv2, np
        self.backend = backend
        self.net = None
        self.ort_session = None
        if backend == "opencv":
            self.net = cv2.dnn.readNetFromONNX(np.frombuffer(blob, dtype=np.uint8))
            self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        else:
            # Explicit opt-in only: a missing Core ML provider must fail closed.
            # ORT may execute individual unsupported nodes on CPU; end-to-end
            # latency and output equivalence must still be checked per device.
            import onnxruntime as ort

            require("CoreMLExecutionProvider" in ort.get_available_providers())
            self.ort_session = ort.InferenceSession(
                blob,
                providers=["CoreMLExecutionProvider", "CPUExecutionProvider"],
                provider_options=[
                    {
                        "ModelFormat": "MLProgram",
                        "MLComputeUnits": "ALL",
                        "RequireStaticInputShapes": "1",
                    },
                    {},
                ],
            )
            require("CoreMLExecutionProvider" in self.ort_session.get_providers())
            inputs = self.ort_session.get_inputs()
            outputs = self.ort_session.get_outputs()
            require(len(inputs) == 1 and inputs[0].shape == [1, 3, 640, 640])
            require(len(outputs) == 1 and outputs[0].shape == [1, 8400, 85])
            self.ort_input_name = inputs[0].name
        self.grids = np.array(
            [
                (x, y)
                for stride in (8, 16, 32)
                for y in range(640 // stride)
                for x in range(640 // stride)
            ],
            dtype=np.float32,
        )
        self.strides = np.array(
            [stride for stride in (8, 16, 32) for _ in range((640 // stride) ** 2)],
            dtype=np.float32,
        )

    def infer(self, rgb, *, lighting):
        enum(lighting, ("daylight", "low_light", "near_dark", "zero_visible"))
        np, cv = self.np, self.cv
        require(type(rgb) is np.ndarray and rgb.dtype == np.uint8 and rgb.ndim == 3)
        h, w, c = rgb.shape
        require(c == 3 and 1 <= w <= 1280 and 1 <= h <= 720)
        if lighting != "daylight":
            return []
        scale = min(640 / w, 640 / h)
        resized = cv.resize(rgb, (int(w * scale), int(h * scale)), interpolation=cv.INTER_LINEAR)
        canvas = np.full((640, 640, 3), 114, dtype=np.uint8)
        canvas[: resized.shape[0], : resized.shape[1]] = resized
        tensor = np.ascontiguousarray(canvas.transpose(2, 0, 1)[None], dtype=np.float32)
        if self.backend == "coreml":
            raw = self.ort_session.run(None, {self.ort_input_name: tensor})[0]
        else:
            self.net.setInput(tensor)
            try:
                raw = self.net.forward()
            finally:
                # Release native input reference; not a secure memory-erasure claim.
                self.net.setInput(np.zeros((1, 3, 640, 640), dtype=np.float32))
        require(raw.shape == (1, 8400, 85) and np.isfinite(raw).all())
        values = raw[0]
        scores = values[:, 4, None] * values[:, 5:]
        categories = np.argmax(scores, axis=1)
        confidence = scores[np.arange(8400), categories]
        candidates = []
        for idx in np.flatnonzero(confidence >= 0.35):
            category = int(categories[idx])
            kind = safe_class(category)
            if kind is None:
                continue
            stride = float(self.strides[idx])
            cx, cy = (values[idx, :2] + self.grids[idx]) * stride / scale
            # Bound exponent before numeric overflow; a malformed output is an error.
            require(bool(np.abs(values[idx, 2:4]).max() <= 20))
            bw, bh = np.exp(values[idx, 2:4]) * stride / scale
            left, top = max(0.0, float(cx - bw / 2)), max(0.0, float(cy - bh / 2))
            right, bottom = min(float(w), float(cx + bw / 2)), min(float(h), float(cy + bh / 2))
            if right <= left or bottom <= top:
                continue
            score = float(confidence[idx])
            require(0 <= score <= 1)
            candidates.append((category, [left, top, right - left, bottom - top], score, kind))
        keep = []
        for category in sorted({v[0] for v in candidates}):
            group = [v for v in candidates if v[0] == category]
            indices = cv.dnn.NMSBoxes([v[1] for v in group], [v[2] for v in group], 0.35, 0.5)
            keep.extend(group[int(i)] for i in indices)
        keep.sort(key=lambda v: (-v[2], v[0], v[1]))
        return [
            {
                "class": kind,
                "box": [box[0] / w, box[1] / h, box[2] / w, box[3] / h],
                "score": score,
                "variance": 0.0001,
                "range_m": None,
            }
            for _, box, score, kind in keep[:32]
        ]
