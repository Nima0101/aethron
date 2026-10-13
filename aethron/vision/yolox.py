"""Pinned OpenCV Zoo RGB detector. No identity features, history or arbitrary-model loader."""

import hashlib
from contextlib import contextmanager, nullcontext
from pathlib import Path
from threading import Lock

from ..schema import enum, require

MODEL_SHA256 = "c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063"
MODEL_BYTES = 35858002


class InferenceCancelled(RuntimeError):
    """Explicit caller cancellation; no observations may be admitted."""

    def __init__(self):
        super().__init__("inference_cancelled")


class InferenceCancellation:
    """One-shot, thread-safe cancellation for one ORT load or inference call.

    Pass to RGBDetector or its infer method and call cancel() from the
    caller's thread. Requests native termination, without a stop-time guarantee.
    Cancellation before final result admission rejects even native success;
    cancellation after admission cannot revoke the result. No helper thread,
    deadline or OpenCV preemption is provided. Use a fresh token for each call.
    """

    def __init__(self):
        self._lock = Lock()
        self._cancelled = False
        self._used = False
        self._options = None
        self._loading = False

    def cancel(self):
        with self._lock:
            self._cancelled = True
            if self._options is not None:
                if self._loading:
                    self._options.set_load_cancellation_flag(True)
                else:
                    self._options.terminate = True

    def _check(self):
        with self._lock:
            if self._cancelled:
                raise InferenceCancelled()

    @contextmanager
    def _call(self, *, load=False):
        with self._lock:
            require(not self._used)
            if self._cancelled:
                raise InferenceCancelled()
            self._used = True
            import onnxruntime as ort

            self._loading = load
            self._options = ort.SessionOptions() if load else ort.RunOptions()
        try:
            yield self._options
            self._check()
        finally:
            # Never retain the provider options after success or failure. Native
            # errors propagate unchanged; cancellation must not trigger a retry.
            with self._lock:
                self._options = None


def _require_coreml_providers(session):
    """Check registered precedence; this is not native node-placement evidence."""
    providers = session.get_providers()
    require(
        type(providers) is list
        and len(providers) == 2
        and all(type(provider) is str for provider in providers)
        and providers == ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    )


def _ort_tensor_name(nodes, expected_shape):
    """Validate the pinned tensor contract before accepting an ORT session."""
    require(type(nodes) is list and len(nodes) == 1)
    node = nodes[0]
    shape = getattr(node, "shape", None)
    tensor_type = getattr(node, "type", None)
    name = getattr(node, "name", None)
    require(
        type(shape) is list
        and len(shape) == len(expected_shape)
        and all(type(dimension) is int for dimension in shape)
        and shape == expected_shape
    )
    require(type(tensor_type) is str and tensor_type == "tensor(float)")
    require(type(name) is str and bool(name))
    return name


def _packed_rgb(canvas):
    """Use packing contract 1 when installed; older validators remain compatible."""
    import numpy as np

    try:
        import aethron_vision_native as native
    except ModuleNotFoundError as error:
        if error.name != "aethron_vision_native":
            raise
    else:
        require(native.CONTRACT_VERSION == 1)
        version = getattr(native, "PACK_CONTRACT_VERSION", None)
        if version is not None:
            require(type(version) is int and version == 1)
            tensor = np.empty((1, 3, 640, 640), dtype=np.float32)
            require(native.pack_rgb(canvas, tensor) is True)
            return tensor
    return np.ascontiguousarray(canvas.transpose(2, 0, 1)[None], dtype=np.float32)


def _validated_output(raw):
    """Admit the pinned float tensor before any confidence arithmetic."""
    import numpy as np

    require(type(raw) is np.ndarray and raw.dtype == np.float32)
    require(raw.shape == (1, 8400, 85))
    if raw.flags.c_contiguous:
        try:
            import aethron_vision_native as native
        except ModuleNotFoundError as error:
            # Missing optional package is supported; a broken installed package
            # or a native rejection must never silently select another checker.
            if error.name != "aethron_vision_native":
                raise
        else:
            require(native.CONTRACT_VERSION == 1)
            require(native.validate_output(raw) is True)
            return raw[0]
    values = raw[0]
    probabilities = values[:, 4:]
    require(bool(np.isfinite(values[:, :4]).all()))
    require(bool(probabilities.min() >= 0 and probabilities.max() <= 1))
    return values


def _selected_scores(raw):
    """Reduce already-admitted products; retain old-package and strided support."""
    import numpy as np

    if raw.flags.c_contiguous:
        try:
            import aethron_vision_native as native
        except ModuleNotFoundError as error:
            if error.name != "aethron_vision_native":
                raise
        else:
            require(native.CONTRACT_VERSION == 1)
            version = getattr(native, "SCORE_CONTRACT_VERSION", None)
            if version is not None:
                require(type(version) is int and version == 1)
                # Subnormal objectness is admitted but measured slower in the
                # native reduction. Select NumPy before execution, not on error.
                objectness = raw[0, :, 4]
                subnormal = (objectness > 0) & (objectness < np.finfo(np.float32).tiny)
                if not bool(subnormal.any()):
                    result = native.select_scores(raw)
                    require(type(result) is tuple and len(result) == 2)
                    require(type(result[0]) is bytes and len(result[0]) == 8400)
                    require(type(result[1]) is bytes and len(result[1]) == 33600)
                    categories = np.frombuffer(result[0], dtype=np.uint8)
                    confidence = np.frombuffer(result[1], dtype=np.float32)
                    require(bool((categories < 80).all()))
                    require(bool(confidence.min() >= 0 and confidence.max() <= 1))
                    return categories, confidence
    values = raw[0]
    scores = values[:, 4, None] * values[:, 5:]
    categories = np.argmax(scores, axis=1)
    return categories, scores[np.arange(8400), categories]


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
    def __init__(self, model_path, *, backend="opencv", cancellation=None):
        require(
            cancellation is None
            or (type(cancellation) is InferenceCancellation and backend == "coreml")
        )
        scope = nullcontext() if cancellation is None else cancellation._call(load=True)
        with scope as load_options:
            self._initialize(model_path, backend=backend, load_options=load_options)

    def _initialize(self, model_path, *, backend, load_options):
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
            # Bound ORT-managed CPU pools instead of sizing them from the host.
            # Provider-internal threads and inference deadlines remain separate.
            options = ort.SessionOptions() if load_options is None else load_options
            options.intra_op_num_threads = 1
            options.inter_op_num_threads = 1
            options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
            options.add_session_config_entry("session.intra_op.allow_spinning", "0")
            options.add_session_config_entry("session.inter_op.allow_spinning", "0")
            self.ort_session = ort.InferenceSession(
                blob,
                sess_options=options,
                # Disable construction retry too: the post-construction call
                # cannot prevent an earlier CPU rebuild or native error print.
                enable_fallback=False,
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
            # An EP execution failure must reach the worker's model_error path,
            # never rebuild/retry the session on CPU under a Core ML label.
            self.ort_session.disable_fallback()
            _require_coreml_providers(self.ort_session)
            inputs = self.ort_session.get_inputs()
            outputs = self.ort_session.get_outputs()
            self.ort_input_name = _ort_tensor_name(inputs, [1, 3, 640, 640])
            _ort_tensor_name(outputs, [1, 8400, 85])
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

    def infer(self, rgb, *, lighting, cancellation=None):
        require(
            cancellation is None
            or (type(cancellation) is InferenceCancellation and self.backend == "coreml")
        )
        scope = nullcontext() if cancellation is None else cancellation._call()
        with scope as run_options:
            return self._infer(
                rgb, lighting=lighting, run_options=run_options, cancellation=cancellation
            )

    def _infer(self, rgb, *, lighting, run_options, cancellation):
        enum(lighting, ("daylight", "low_light", "near_dark", "zero_visible"))
        np, cv = self.np, self.cv
        require(type(rgb) is np.ndarray and rgb.dtype == np.uint8 and rgb.ndim == 3)
        h, w, c = rgb.shape
        require(c == 3 and 1 <= w <= 1280 and 1 <= h <= 720)
        if lighting != "daylight":
            return []
        scale = min(640 / w, 640 / h)
        resize_width, resize_height = int(w * scale), int(h * scale)
        # Extreme aspect ratios can round an admitted one-pixel axis to zero.
        # Reject before the native resize; never clamp or change pixel geometry.
        require(resize_width > 0 and resize_height > 0)
        resized = cv.resize(rgb, (resize_width, resize_height), interpolation=cv.INTER_LINEAR)
        canvas = np.full((640, 640, 3), 114, dtype=np.uint8)
        canvas[: resized.shape[0], : resized.shape[1]] = resized
        tensor = _packed_rgb(canvas)
        if self.backend == "coreml":
            # Reassert the application policy if fallback was enabled between calls.
            self.ort_session.disable_fallback()
            _require_coreml_providers(self.ort_session)
            if cancellation is not None:
                cancellation._check()
            outputs = self.ort_session.run(None, {self.ort_input_name: tensor}, run_options)
            if cancellation is not None:
                cancellation._check()
            # Withdraw results on observed drift. Do not mask an execution
            # exception with a finally check or retry under a different provider.
            _require_coreml_providers(self.ort_session)
            require(type(outputs) is list and len(outputs) == 1)
            raw = outputs[0]
        else:
            try:
                self.net.setInput(tensor)
                raw = self.net.forward()
            finally:
                # Attempt replacement even if setInput partially succeeded then
                # raised. This does not guarantee release or secure memory erasure.
                self.net.setInput(np.zeros((1, 3, 640, 640), dtype=np.float32))
        values = _validated_output(raw)
        categories, confidence = _selected_scores(raw)
        candidates = []
        for idx in np.flatnonzero(confidence >= 0.35):
            category = int(categories[idx])
            kind = safe_class(category)
            if kind is None:
                continue
            stride = float(self.strides[idx])
            # Finite model values can still overflow during decoding. Reject
            # before clipping can disguise that failure as an offscreen box.
            try:
                with np.errstate(over="raise", invalid="raise"):
                    cx, cy = (values[idx, :2] + self.grids[idx]) * stride / scale
            except FloatingPointError:
                raise ValueError("invalid_input") from None
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
            # The pinned binding returns an empty tuple or a flat vector<int>.
            # Validate before indexing: Python accepts negative indices and int()
            # would silently truncate malformed native floating-point values.
            if type(indices) is tuple:
                require(len(indices) == 0)
            else:
                require(type(indices) is np.ndarray and indices.dtype == np.int32)
                require(indices.ndim == 1 and indices.size <= len(group))
                require(bool(((indices >= 0) & (indices < len(group))).all()))
                require(len(set(indices.tolist())) == indices.size)
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
