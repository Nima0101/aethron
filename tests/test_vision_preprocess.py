"""Pinned pixel preparation: channel order, top-left padding and native admission."""

import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from aethron.vision.yolox import RGBDetector

AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "cv2"))


@unittest.skipUnless(AVAILABLE, "optional pinned vision dependencies required")
class VisionPreprocess(unittest.TestCase):
    def setUp(self):
        import cv2
        import numpy as np

        cv2.setNumThreads(1)
        self.np = np
        self.inputs = []
        self.detector = RGBDetector.__new__(RGBDetector)
        self.detector.cv, self.detector.np = cv2, np
        self.detector.backend = "opencv"
        self.detector.grids = np.zeros((8400, 2), dtype=np.float32)
        self.detector.strides = np.full(8400, 8, dtype=np.float32)
        self.detector.net = SimpleNamespace(
            setInput=self.inputs.append,
            forward=lambda: np.zeros((1, 8400, 85), dtype=np.float32),
        )

    def test_zero_resize_extent_rejected_before_native_execution(self):
        for height, width in ((1, 641), (641, 1), (1, 1280), (720, 1)):
            with self.subTest(shape=(height, width)):
                pixels = self.np.zeros((height, width, 3), dtype=self.np.uint8)
                with patch.object(
                    self.detector.cv, "resize", wraps=self.detector.cv.resize
                ) as resize:
                    with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                        self.detector.infer(pixels, lighting="daylight")
                    resize.assert_not_called()
                self.assertEqual(self.inputs, [])

    def test_constant_channels_and_fractional_padding_are_exact(self):
        np = self.np
        for height, width, resized_height in ((1, 1, 640), (359, 641, 358), (720, 1280, 360)):
            self.inputs.clear()
            pixels = np.empty((height, width, 3), dtype=np.uint8)
            pixels[:] = (17, 89, 203)
            self.assertEqual(self.detector.infer(pixels, lighting="daylight"), [])
            tensor = self.inputs[0]
            self.assertEqual(tensor.shape, (1, 3, 640, 640))
            self.assertEqual(tensor.dtype, np.float32)
            self.assertTrue(tensor.flags.c_contiguous)
            for channel, value in enumerate((17, 89, 203)):
                self.assertTrue((tensor[0, channel, :resized_height, :] == value).all())
                self.assertTrue((tensor[0, channel, resized_height:, :] == 114).all())
            self.assertEqual(len(self.inputs), 2)
            self.assertTrue((self.inputs[1] == 0).all())
            self.assertFalse(np.shares_memory(tensor, pixels))

    def test_noncontiguous_readonly_pixels_preserve_channel_order(self):
        np = self.np
        pixels = np.zeros((640, 640, 3), dtype=np.uint8)
        pixels[:, :320] = (1, 2, 3)
        pixels[:, 320:] = (4, 5, 6)
        pixels = pixels[:, ::-1]
        pixels.setflags(write=False)
        self.detector.infer(pixels, lighting="daylight")
        tensor = self.inputs[0]
        for channel in range(3):
            self.assertTrue((tensor[0, channel, :, :320] == channel + 4).all())
            self.assertTrue((tensor[0, channel, :, 320:] == channel + 1).all())

    def test_darkness_does_not_prepare_or_execute_rgb(self):
        pixels = self.np.zeros((1, 1280, 3), dtype=self.np.uint8)
        for lighting in ("low_light", "near_dark", "zero_visible"):
            self.assertEqual(self.detector.infer(pixels, lighting=lighting), [])
        self.assertEqual(self.inputs, [])
