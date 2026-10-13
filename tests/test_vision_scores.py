"""Production score selection preserves the admitted float32 decision boundary."""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

try:
    import numpy as np
except ModuleNotFoundError:
    np = None

from aethron.vision import yolox


@unittest.skipIf(np is None, "optional NumPy required")
class VisionScores(unittest.TestCase):
    def select(self, raw):
        self.assertTrue(hasattr(yolox, "_selected_scores"), "score dispatcher missing")
        return yolox._selected_scores(raw)

    def test_portable_strided_and_old_package_parity(self):
        raw = np.random.default_rng(10).random((1, 8400, 85), dtype=np.float32)
        for value in (raw, raw[:, ::-1]):
            products = value[0, :, 4, None] * value[0, :, 5:]
            expected = products.argmax(axis=1)
            for module in (None, SimpleNamespace(CONTRACT_VERSION=1)):
                with patch.dict(sys.modules, {"aethron_vision_native": module}):
                    cat, confidence = self.select(value)
                np.testing.assert_array_equal(cat, expected)
                np.testing.assert_array_equal(confidence, products[np.arange(8400), expected])

    def test_broken_declared_native_contract_never_falls_back(self):
        raw = np.zeros((1, 8400, 85), dtype=np.float32)
        for version, result in ((2, None), (True, None), (1, (b"", b"")), (1, None)):
            module = SimpleNamespace(
                CONTRACT_VERSION=1,
                SCORE_CONTRACT_VERSION=version,
                select_scores=lambda value, result=result: result,
            )
            with patch.dict(sys.modules, {"aethron_vision_native": module}):
                with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                    self.select(raw)

    def test_selected_bits_match_portable_at_threshold_and_ties(self):
        raw = np.zeros((1, 8400, 85), dtype=np.float32)
        raw[0, :3, 4] = 1
        t = np.float32(0.35)
        raw[0, :3, 5] = [np.nextafter(t, np.float32(0)), t, np.nextafter(t, np.float32(1))]
        for subnormal in (False, True):
            if subnormal:
                raw[0, 3, 4] = np.nextafter(np.float32(0), np.float32(1))
                raw[0, 3, 6] = 0.25
            cat, scores = self.select(raw)
            np.testing.assert_array_equal(cat[:4], [0, 0, 0, 0])
            np.testing.assert_array_equal(np.flatnonzero(scores >= t), [1, 2])
            with patch.dict(sys.modules, {"aethron_vision_native": None}):
                old_cat, old_scores = self.select(raw)
            np.testing.assert_array_equal(cat, old_cat)
            np.testing.assert_array_equal(scores.view(np.uint32), old_scores.view(np.uint32))

    def test_native_errors_and_invalid_results_never_retry(self):
        raw = np.zeros((1, 8400, 85), dtype=np.float32)
        error = RuntimeError("score_failed")
        invalid = [
            (bytes([80]) * 8400, bytes(33600)),
            (bytes(8400), np.full(8400, np.nan, dtype=np.float32).tobytes()),
            (bytes(8400), np.full(8400, -0.1, dtype=np.float32).tobytes()),
            (bytes(8400), np.full(8400, 1.1, dtype=np.float32).tobytes()),
            (bytearray(8400), bytes(33600)),
        ]
        for result in [error, *invalid]:
            with self.subTest(result_type=type(result)):
                select = Mock(side_effect=error) if result is error else Mock(return_value=result)
                native = SimpleNamespace(
                    CONTRACT_VERSION=1, SCORE_CONTRACT_VERSION=1, select_scores=select
                )
                with (
                    patch.dict(sys.modules, {"aethron_vision_native": native}),
                    patch.object(np, "argmax") as portable,
                ):
                    with self.assertRaises(
                        RuntimeError if result is error else ValueError
                    ) as raised:
                        self.select(raw)
                portable.assert_not_called()
                self.assertEqual(select.call_count, 1)
                self.assertIs(select.call_args.args[0], raw)
                if result is error:
                    self.assertIs(raised.exception, error)

    def test_subnormal_and_strided_inputs_select_portable_before_native_call(self):
        raw = np.zeros((1, 8400, 85), dtype=np.float32)
        raw[0, 0, 4] = np.nextafter(np.float32(0), np.float32(1))
        raw[0, 0, 6] = 0.25
        native = SimpleNamespace(CONTRACT_VERSION=1, SCORE_CONTRACT_VERSION=1, select_scores=Mock())
        for value in (raw, raw[:, ::-1]):
            with patch.dict(sys.modules, {"aethron_vision_native": native}):
                categories, scores = self.select(value)
            np.testing.assert_array_equal(categories, np.zeros(8400))
            np.testing.assert_array_equal(scores, np.zeros(8400))
        native.select_scores.assert_not_called()

    def test_native_score_failure_cannot_become_an_empty_detection(self):
        from aethron.vision.yolox import RGBDetector

        raw = np.zeros((1, 8400, 85), dtype=np.float32)
        detector = RGBDetector.__new__(RGBDetector)
        detector.np = np
        detector.cv = SimpleNamespace(
            INTER_LINEAR=1, resize=lambda pixels, size, interpolation: pixels
        )
        detector.backend = "opencv"
        detector.net = SimpleNamespace(setInput=Mock(), forward=Mock(return_value=raw))
        error = RuntimeError("score_failed")
        native = SimpleNamespace(
            CONTRACT_VERSION=1,
            SCORE_CONTRACT_VERSION=1,
            validate_output=lambda value: True,
            select_scores=Mock(side_effect=error),
        )
        with patch.dict(sys.modules, {"aethron_vision_native": native}):
            with self.assertRaises(RuntimeError) as raised:
                detector.infer(np.zeros((640, 640, 3), dtype=np.uint8), lighting="daylight")
        self.assertIs(raised.exception, error)
        self.assertEqual(detector.net.forward.call_count, 1)
        self.assertEqual(native.select_scores.call_count, 1)
