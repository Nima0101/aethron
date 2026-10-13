"""Observe OpenCV requests and injected errors without parsing a model."""

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aethron.vision import yolox

AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "cv2"))
MODEL_FIXTURE = b"synthetic OpenCV startup fixture"


@unittest.skipUnless(AVAILABLE, "optional pinned vision dependencies required")
class VisionOpenCV(unittest.TestCase):
    def setUp(self):
        import cv2
        import numpy as np

        self.cv, self.np = cv2, np
        self.calls = Mock()
        self.net = SimpleNamespace(
            setPreferableBackend=self.calls.backend,
            setPreferableTarget=self.calls.target,
            setInput=self.calls.input,
            forward=self.calls.forward,
        )
        self.calls.load.return_value = self.net

    def detector(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.onnx"
            path.write_bytes(MODEL_FIXTURE)
            with (
                patch.object(yolox, "MODEL_BYTES", len(MODEL_FIXTURE)),
                patch.object(yolox, "MODEL_SHA256", hashlib.sha256(MODEL_FIXTURE).hexdigest()),
                patch.object(self.cv.dnn, "readNetFromONNX", self.calls.load),
            ):
                return yolox.RGBDetector(path, backend="opencv")

    def test_validated_bytes_request_explicit_opencv_cpu(self):
        detector = self.detector()
        self.calls.load.assert_called_once()
        args, kwargs = self.calls.load.call_args
        self.assertEqual(len(args), 1)
        self.assertEqual(kwargs, {})
        self.assertIs(type(args[0]), self.np.ndarray)
        self.assertEqual(args[0].dtype, self.np.uint8)
        self.assertEqual(args[0].shape, (len(MODEL_FIXTURE),))
        self.assertEqual(args[0].tobytes(), MODEL_FIXTURE)
        self.calls.backend.assert_called_once_with(self.cv.dnn.DNN_BACKEND_OPENCV)
        self.calls.target.assert_called_once_with(self.cv.dnn.DNN_TARGET_CPU)
        self.assertEqual([call[0] for call in self.calls.mock_calls], ["load", "backend", "target"])
        self.assertIs(detector.net, self.net)
        self.assertEqual(detector.backend, "opencv")
        self.assertIsNone(detector.ort_session)

    def test_initialization_failure_stops_without_retry(self):
        stages = ("load", "backend", "target")
        for index, stage in enumerate(stages):
            for error_type in (self.cv.error, RuntimeError):
                with self.subTest(stage=stage, error=error_type.__name__):
                    self.calls.reset_mock(side_effect=True)
                    original = error_type("synthetic startup failure")
                    getattr(self.calls, stage).side_effect = original
                    with self.assertRaises(error_type) as caught:
                        self.detector()
                    self.assertIs(caught.exception, original)
                    self.assertEqual(
                        [call[0] for call in self.calls.mock_calls], list(stages[: index + 1])
                    )

    def test_execution_failures_cannot_retry_or_become_empty_success(self):
        pixels = self.np.zeros((8, 8, 3), dtype=self.np.uint8)
        for stage in ("input", "forward", "release"):
            for error_type in (self.cv.error, RuntimeError):
                with self.subTest(stage=stage, error=error_type.__name__):
                    self.calls.reset_mock(side_effect=True)
                    detector = self.detector()
                    self.calls.reset_mock(side_effect=True)
                    original = error_type("synthetic execution failure")
                    self.calls.input.side_effect = (
                        [original, None]
                        if stage == "input"
                        else [None, original if stage == "release" else None]
                    )
                    self.calls.forward.side_effect = original if stage == "forward" else None
                    with (
                        patch.object(
                            yolox,
                            "_validated_output",
                            side_effect=AssertionError("failed execution reached output admission"),
                        ) as admit,
                        self.assertRaises(error_type) as caught,
                    ):
                        detector.infer(pixels, lighting="daylight")
                    self.assertIs(caught.exception, original)
                    admit.assert_not_called()
                    expected = (
                        ["input", "input"] if stage == "input" else ["input", "forward", "input"]
                    )
                    self.assertEqual([call[0] for call in self.calls.mock_calls], expected)
                    release = self.calls.input.call_args.args[0]
                    self.assertEqual(release.shape, (1, 3, 640, 640))
                    self.assertEqual(release.dtype, self.np.float32)
                    self.assertFalse(release.any())

    def test_partially_accepted_input_is_replaced_after_failure(self):
        detector = self.detector()
        pixels = self.np.full((8, 8, 3), 71, dtype=self.np.uint8)
        retained = []
        original = self.cv.error("synthetic failure after input copy")

        def partial_input(tensor):
            retained[:] = [tensor.copy()]
            if self.calls.input.call_count == 1:
                raise original

        self.calls.input.side_effect = partial_input
        with self.assertRaises(self.cv.error) as caught:
            detector.infer(pixels, lighting="daylight")
        self.assertIs(caught.exception, original)
        self.calls.forward.assert_not_called()
        self.assertEqual(self.calls.input.call_count, 2)
        self.assertFalse(retained[0].any())

    def test_input_and_replacement_failures_preserve_both_errors(self):
        detector = self.detector()
        original = self.cv.error("synthetic input failure")
        cleanup = RuntimeError("synthetic replacement failure")
        self.calls.input.side_effect = [original, cleanup]
        with self.assertRaises(RuntimeError) as caught:
            detector.infer(self.np.zeros((8, 8, 3), dtype=self.np.uint8), lighting="daylight")
        self.assertIs(caught.exception, cleanup)
        self.assertIs(caught.exception.__context__, original)
        self.calls.forward.assert_not_called()
        self.assertEqual(self.calls.input.call_count, 2)

    def test_simultaneous_execution_and_cleanup_errors_preserve_failure_context(self):
        pixels = self.np.zeros((8, 8, 3), dtype=self.np.uint8)
        for execution_type in (self.cv.error, RuntimeError):
            for cleanup_type in (self.cv.error, RuntimeError):
                with self.subTest(execution=execution_type.__name__, cleanup=cleanup_type.__name__):
                    self.calls.reset_mock(side_effect=True)
                    detector = self.detector()
                    self.calls.reset_mock(side_effect=True)
                    execution_error = execution_type("synthetic inference failure")
                    cleanup_error = cleanup_type("synthetic cleanup failure")
                    self.calls.forward.side_effect = execution_error
                    self.calls.input.side_effect = [None, cleanup_error]
                    with (
                        patch.object(
                            yolox,
                            "_validated_output",
                            side_effect=AssertionError("failed execution reached output admission"),
                        ) as admit,
                        self.assertRaises(cleanup_type) as caught,
                    ):
                        detector.infer(pixels, lighting="daylight")
                    self.assertIs(caught.exception, cleanup_error)
                    self.assertIs(caught.exception.__context__, execution_error)
                    admit.assert_not_called()
                    self.assertEqual(
                        [call[0] for call in self.calls.mock_calls], ["input", "forward", "input"]
                    )
