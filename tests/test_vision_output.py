"""Malformed native outputs cannot become detections or apparent empty success."""

import importlib.util
import random
import unittest
from types import SimpleNamespace

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
