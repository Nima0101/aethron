"""Malformed native outputs cannot become detections or apparent empty success."""

import builtins
import importlib.util
import random
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from aethron.vision.yolox import RGBDetector, _validated_output

AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "cv2"))


@unittest.skipUnless(AVAILABLE, "optional pinned vision dependencies required")
class VisionOutput(unittest.TestCase):
    def setUp(self):
        import cv2
        import numpy as np

        cv2.setNumThreads(1)
        self.np = np
        # Only the native forward is substituted; infer runs its real pixel
        # preparation, output admission, score multiplication and NMS.
        self.detector = RGBDetector.__new__(RGBDetector)
        self.detector.cv, self.detector.np = cv2, np
        self.detector.backend = "opencv"
        self.detector.grids = np.zeros((8400, 2), dtype=np.float32)
        self.detector.strides = np.full(8400, 8, dtype=np.float32)
        self.pixels = np.zeros((64, 64, 3), dtype=np.uint8)

    def output(self):
        raw = self.np.zeros((1, 8400, 85), dtype=self.np.float32)
        raw[0, 0, :2] = 4
        return raw

    def infer(self, raw):
        self.detector.net = SimpleNamespace(setInput=lambda tensor: None, forward=lambda: raw)
        return self.detector.infer(self.pixels, lighting="daylight")

    def test_negative_factors_cannot_create_positive_person_score(self):
        raw = self.output()
        raw[0, 0, 4:6] = -0.8
        with self.assertRaises(ValueError):
            self.infer(raw)

    def test_invalid_probability_cannot_hide_in_unselected_row_or_class(self):
        for row, column, value in ((8399, 4, -0.1), (8399, 84, 1.01), (0, 5, -0.1)):
            with self.subTest(row=row, column=column, value=value):
                raw = self.output()
                raw[0, row, column] = value
                with self.assertRaises(ValueError):
                    self.infer(raw)

    def test_wrong_native_dtype_cannot_be_empty_success(self):
        for dtype in (self.np.bool_, self.np.uint8, self.np.float64, object):
            with self.subTest(dtype=dtype):
                with self.assertRaises(ValueError):
                    self.infer(self.output().astype(dtype))

    def test_nonfinite_geometry_and_probabilities_fail_closed(self):
        for column in (0, 3, 4, 84):
            for value in (float("nan"), float("inf"), -float("inf")):
                with self.subTest(column=column, value=value):
                    raw = self.output()
                    raw[0, 8399, column] = value
                    with self.assertRaises(ValueError):
                        self.infer(raw)

    def test_valid_boundary_probabilities_preserve_detection_and_empty_result(self):
        raw = self.output()
        self.assertEqual(self.infer(raw), [])
        raw[0, 0, 4:6] = 1
        detections = self.infer(raw)
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0]["class"], "person")
        self.assertEqual(detections[0]["score"], 1)
        for actual, expected in zip(detections[0]["box"], (0.04375, 0.04375, 0.0125, 0.0125)):
            self.assertAlmostEqual(actual, expected, places=6)

    def test_finite_centres_cannot_overflow_into_empty_success(self):
        np = self.np
        for policy in ("ignore", "warn", "raise"):
            for column in (0, 1):
                for sign in (-1, 1):
                    with self.subTest(policy=policy, column=column, sign=sign):
                        raw = self.output()
                        raw[0, 0, 4:6] = 1
                        raw[0, 0, column] = sign * np.finfo(np.float32).max
                        with np.errstate(over=policy):
                            before = np.geterr()
                            with patch.object(self.detector.cv.dnn, "NMSBoxes") as nms:
                                with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                                    self.infer(raw)
                            self.assertEqual(np.geterr(), before)
                        nms.assert_not_called()

    def test_rescaling_overflow_withdraws_other_valid_candidates(self):
        np = self.np
        self.pixels = np.zeros((64, 1280, 3), dtype=np.uint8)
        raw = self.output()
        raw[0, :2, :2] = 4
        raw[0, :2, 4:6] = 1
        # Multiplication by stride 8 is finite; division by scale 0.5 overflows.
        raw[0, 1, 0] = np.finfo(np.float32).max / np.float32(8)
        with np.errstate(over="ignore"):
            with patch.object(self.detector.cv.dnn, "NMSBoxes") as nms:
                with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                    self.infer(raw)
        nms.assert_not_called()

    def test_finite_offscreen_centres_remain_empty(self):
        for column in (0, 1):
            for sign in (-1, 1):
                with self.subTest(column=column, sign=sign):
                    raw = self.output()
                    raw[0, 0, 4:6] = 1
                    raw[0, 0, column] = sign * 1e30
                    self.assertEqual(self.infer(raw), [])

    def test_valid_decoding_preserves_clipping_and_classwise_nms(self):
        raw = self.output()
        raw[0, :3, :2] = 0
        raw[0, :3, 4] = 1
        raw[0, :2, 5] = 1  # Identical person boxes suppress to one.
        raw[0, 2, 7] = 1  # Same box, COCO car class: kept separately.
        detections = self.infer(raw)
        self.assertEqual([d["class"] for d in detections], ["person", "vehicle"])
        for detection in detections:
            self.assertEqual(detection["score"], 1)
            for actual, expected in zip(detection["box"], (0, 0, 0.00625, 0.00625)):
                self.assertAlmostEqual(actual, expected, places=8)

    def test_nms_rejects_negative_out_of_range_and_duplicate_indices(self):
        np = self.np
        raw = self.output()
        raw[0, :2, :2] = ((4, 4), (20, 20))
        raw[0, :2, 4:6] = 1
        for values in ([-1], [2], [0, 0], [0, 1, 0], [0, 2]):
            with self.subTest(indices=values):
                indices = np.array(values, dtype=np.int32)
                with patch.object(self.detector.cv.dnn, "NMSBoxes", return_value=indices) as nms:
                    with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                        self.infer(raw)
                nms.assert_called_once()

    def test_nms_rejects_malformed_native_index_containers(self):
        np = self.np
        raw = self.output()
        raw[0, 0, 4:6] = 1
        invalid = (
            None,
            [0],
            (0,),
            "0",
            {},
            np.array(0, dtype=np.int32),
            np.array([[0]], dtype=np.int32),
            np.array([False]),
            np.array([0.9], dtype=np.float32),
            np.array([0], dtype=np.int64),
            np.array([0], dtype=object),
            np.array([], dtype=np.float32),
        )
        for indices in invalid:
            with self.subTest(container=type(indices), dtype=getattr(indices, "dtype", None)):
                with patch.object(self.detector.cv.dnn, "NMSBoxes", return_value=indices):
                    with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                        self.infer(raw)

    def test_late_nms_rejection_withdraws_previously_selected_class(self):
        np = self.np
        raw = self.output()
        raw[0, :2, :2] = 4
        raw[0, :2, 4] = 1
        raw[0, 0, 5] = 1  # Person group succeeds first.
        raw[0, 1, 7] = 1  # Vehicle group returns an invalid local index.
        results = [np.array([0], dtype=np.int32), np.array([-1], dtype=np.int32)]
        with patch.object(self.detector.cv.dnn, "NMSBoxes", side_effect=results) as nms:
            with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                self.infer(raw)
        self.assertEqual(nms.call_count, 2)

    def test_nms_empty_results_and_existing_score_boundary_are_preserved(self):
        np = self.np
        raw = self.output()
        raw[0, 0, 4:6] = 1
        for indices in ((), np.array([], dtype=np.int32)):
            with patch.object(self.detector.cv.dnn, "NMSBoxes", return_value=indices):
                self.assertEqual(self.infer(raw), [])
        # Keep the pinned native strict score comparison, including float32
        # rounding at 0.35; index admission must not tune the frozen threshold.
        raw[0, 0, 5] = np.float32(0.35)
        self.assertEqual(self.infer(raw), [])
        raw[0, 0, 5] = np.nextafter(np.float32(0.35), np.float32(1))
        self.assertEqual(len(self.infer(raw)), 1)

    def test_nms_error_propagates_once_without_retry(self):
        raw = self.output()
        raw[0, 0, 4:6] = 1
        error = RuntimeError("injected NMS failure")
        with patch.object(self.detector.cv.dnn, "NMSBoxes", side_effect=error) as nms:
            with self.assertRaises(RuntimeError) as caught:
                self.infer(raw)
        self.assertIs(caught.exception, error)
        nms.assert_called_once()

    def test_native_nms_preserves_score_order_and_final_detection_bound(self):
        raw = self.output()
        for row in range(40):
            raw[0, row, :2] = (4 + 10 * (row % 8), 4 + 10 * (row // 8))
            raw[0, row, 4] = 1
            raw[0, row, 5] = 0.4 + row * 0.01
        detections = self.infer(raw)
        self.assertEqual(len(detections), 32)
        self.assertEqual([d["score"] for d in detections], raw[0, 8:40, 5][::-1].tolist())
        self.assertTrue(all(d["class"] == "person" for d in detections))
        self.assertEqual(len({tuple(d["box"]) for d in detections}), 32)

    def test_seeded_probability_mutations_raise_fixed_error(self):
        rng = random.Random(20261010)
        np = self.np
        invalid = (
            np.nextafter(np.float32(0), np.float32(-1)),
            np.nextafter(np.float32(1), np.float32(2)),
            float("nan"),
            float("inf"),
        )
        raw = self.output()
        for _ in range(64):
            row, column = rng.randrange(8400), rng.randrange(4, 85)
            raw[0, row, column] = rng.choice(invalid)
            with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                _validated_output(raw)
            raw[0, row, column] = 0
        self.assertEqual(self.infer(raw), [])

    def test_wrong_output_container_and_shape_raise_fixed_error(self):
        for raw in (None, [], {}, self.np.zeros((1, 8401, 85), dtype=self.np.float32)):
            with self.subTest(kind=type(raw)):
                with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                    _validated_output(raw)

    def test_native_failure_or_rejection_never_falls_back(self):
        def fail(raw):
            raise RuntimeError("synthetic native failure")

        for function, version, error in (
            (lambda raw: False, 1, ValueError),
            (lambda raw: True, 2, ValueError),
            (fail, 1, RuntimeError),
        ):
            module = SimpleNamespace(CONTRACT_VERSION=version, validate_output=function)
            with patch.dict(sys.modules, {"aethron_vision_native": module}):
                with self.assertRaises(error):
                    _validated_output(self.output())

    def test_portable_layouts_preserve_view_and_reject_nonfinite_bits(self):
        np = self.np
        raw = np.zeros((1, 8400, 85), dtype=np.float32)
        for data in (raw, np.asfortranarray(raw), raw[:, ::-1, ::-1]):
            with patch.dict(sys.modules, {"aethron_vision_native": None}):
                self.assertTrue(np.shares_memory(data, _validated_output(data)))
                for bits in (0x7F800001, 0x7FC00000, 0x7F800000, 0xFF800000):
                    data.view(np.uint32)[0, 8399, 84] = bits
                    with np.errstate(all="raise"):
                        with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                            _validated_output(data)
                    data[0, 8399, 84] = 0

    def test_broken_native_dependency_never_selects_portable_checker(self):
        original_import = builtins.__import__
        error = ModuleNotFoundError("missing native dependency", name="_bounds")

        def import_module(name, *args, **kwargs):
            if name == "aethron_vision_native":
                raise error
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_module):
            with self.assertRaises(ModuleNotFoundError) as caught:
                _validated_output(self.output())
        self.assertIs(caught.exception, error)

    def test_native_success_receives_original_buffer_and_returns_view(self):
        raw = self.output()
        calls = []

        def validate(value):
            calls.append(value)
            return True

        module = SimpleNamespace(CONTRACT_VERSION=1, validate_output=validate)
        with patch.dict(sys.modules, {"aethron_vision_native": module}):
            result = _validated_output(raw)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0], raw)
        self.assertTrue(self.np.shares_memory(result, raw))
