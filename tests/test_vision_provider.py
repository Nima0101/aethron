"""Provider failure admission using the real ORT Python fallback mechanism.

Native execution is replaced with a deterministic fault, not an accelerator claim.
"""

import hashlib
import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aethron.vision import yolox

AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "cv2", "onnxruntime"))


@unittest.skipUnless(AVAILABLE, "optional pinned vision/Core ML dependencies required")
class VisionProvider(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from onnxruntime.capi.onnxruntime_inference_collection import Session

        self.np = np
        self.session = Session()
        self.session._providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        self.session._fallback_providers = ["CPUExecutionProvider"]
        self.session._inputs_meta = [
            SimpleNamespace(name="images", shape=[1, 3, 640, 640], type="tensor(float)")
        ]
        self.session._outputs_meta = [
            SimpleNamespace(name="output", shape=[1, 8400, 85], type="tensor(float)")
        ]
        self.pixels = np.zeros((8, 8, 3), dtype=np.uint8)

    def detector(self, available=None, session_factory=None):
        # Keep file length/digest verification real; only native model loading is
        # substituted so no downloaded model or hardware is needed for this fault.
        blob = b"synthetic provider boundary fixture"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.onnx"
            path.write_bytes(blob)
            with (
                patch.object(yolox, "MODEL_BYTES", len(blob)),
                patch.object(yolox, "MODEL_SHA256", hashlib.sha256(blob).hexdigest()),
                patch(
                    "onnxruntime.get_available_providers",
                    return_value=available or ["CoreMLExecutionProvider", "CPUExecutionProvider"],
                ),
                patch(
                    "onnxruntime.InferenceSession",
                    return_value=self.session,
                    side_effect=session_factory,
                ),
            ):
                return yolox.RGBDetector(path, backend="coreml")

    def test_construction_failure_cannot_retry_or_print_native_details(self):
        from onnxruntime.capi.onnxruntime_inference_collection import InferenceSession

        for error_type in (ValueError, RuntimeError):
            with self.subTest(error_type=error_type.__name__):
                attempts = []
                original = error_type("synthetic private native detail")

                def fail(session, providers, *args, attempts=attempts, original=original):
                    attempts.append(tuple(providers))
                    session._fallback_providers = ["CPUExecutionProvider"]
                    raise original

                output = io.StringIO()
                with (
                    patch.object(InferenceSession, "_create_inference_session", fail),
                    redirect_stdout(output),
                    self.assertRaises(error_type) as caught,
                ):
                    self.detector(session_factory=InferenceSession)
                self.assertIs(caught.exception, original)
                self.assertEqual(attempts, [("CoreMLExecutionProvider", "CPUExecutionProvider")])
                self.assertEqual(output.getvalue(), "")

    def test_reenabled_fallback_is_disabled_before_each_execution(self):
        from onnxruntime.capi import _pybind_state as native

        original = native.EPFail("synthetic private provider detail")
        run = Mock(side_effect=original)
        self.session._sess = SimpleNamespace(run=run, is_webgpu_graph_capture_enabled=lambda: False)
        detector = self.detector()
        for attempt in range(2):
            with self.subTest(attempt=attempt):
                run.reset_mock()
                self.session.enable_fallback()
                output = io.StringIO()
                with (
                    patch.object(self.session, "set_providers") as retry,
                    redirect_stdout(output),
                    self.assertRaises(native.EPFail) as caught,
                ):
                    detector.infer(self.pixels, lighting="daylight")
                self.assertIs(caught.exception, original)
                self.assertEqual(output.getvalue(), "")
                run.assert_called_once()
                retry.assert_not_called()

    def test_execution_failure_cannot_retry_on_cpu(self):
        from onnxruntime.capi import _pybind_state as native

        def fail(*args):
            raise native.EPFail("synthetic provider failure")

        def cpu_retry(*args):
            self.session._providers = ["CPUExecutionProvider"]
            self.session._sess = SimpleNamespace(
                is_webgpu_graph_capture_enabled=lambda: False,
                run=lambda *args: [self.np.zeros((1, 8400, 85), dtype=self.np.float32)],
            )

        self.session._sess = SimpleNamespace(
            run=fail, is_webgpu_graph_capture_enabled=lambda: False
        )
        detector = self.detector()
        with patch.object(self.session, "set_providers", side_effect=cpu_retry):
            with self.assertRaises(native.EPFail):
                detector.infer(self.pixels, lighting="daylight")
        self.assertEqual(self.session.get_providers()[0], "CoreMLExecutionProvider")

    def test_session_that_lost_coreml_during_construction_is_rejected(self):
        self.session._providers = ["CPUExecutionProvider"]
        with self.assertRaises(ValueError):
            self.detector()

    def test_missing_coreml_is_rejected(self):
        with self.assertRaises(ValueError):
            self.detector(available=["CPUExecutionProvider"])

    def test_successful_inference_keeps_declared_provider(self):
        self.session._sess = SimpleNamespace(
            is_webgpu_graph_capture_enabled=lambda: False,
            run=lambda *args: [self.np.zeros((1, 8400, 85), dtype=self.np.float32)],
        )
        detector = self.detector()
        self.assertEqual(detector.infer(self.pixels, lighting="daylight"), [])
        self.assertEqual(self.session.get_providers()[0], "CoreMLExecutionProvider")
