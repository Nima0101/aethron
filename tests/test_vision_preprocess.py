"""Pinned pixel preparation: channel order, top-left padding and native admission."""

import importlib.util
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aethron.vision.yolox import RGBDetector, _packed_rgb

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

    def test_native_packing_rejection_never_reaches_inference(self):
        native = SimpleNamespace(
            CONTRACT_VERSION=1,
            PACK_CONTRACT_VERSION=1,
            pack_rgb=lambda source, output: False,
            validate_output=lambda raw: True,
        )
        pixels = self.np.zeros((64, 64, 3), dtype=self.np.uint8)
        with patch.dict(sys.modules, {"aethron_vision_native": native}):
            with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                self.detector.infer(pixels, lighting="daylight")
        self.assertEqual(self.inputs, [])

    def test_absent_and_admission_only_modules_preserve_packing(self):
        canvas = self.np.arange(640 * 640 * 3, dtype=self.np.uint8).reshape(640, 640, 3)
        expected = self.np.ascontiguousarray(canvas.transpose(2, 0, 1)[None], dtype=self.np.float32)
        for native in (None, SimpleNamespace(CONTRACT_VERSION=1)):
            with self.subTest(native=native):
                with patch.dict(sys.modules, {"aethron_vision_native": native}):
                    actual = _packed_rgb(canvas)
                self.np.testing.assert_array_equal(actual, expected)
                self.assertTrue(actual.flags.c_contiguous)
                self.assertFalse(self.np.shares_memory(actual, canvas))

    def test_invalid_contract_and_native_errors_never_retry_or_infer(self):
        pixels = self.np.zeros((64, 64, 3), dtype=self.np.uint8)
        error = RuntimeError("packing_failed")
        for version in (True, 0, 2, "1", 1):
            with self.subTest(version=version):
                pack = Mock(side_effect=error)
                native = SimpleNamespace(
                    CONTRACT_VERSION=1, PACK_CONTRACT_VERSION=version, pack_rgb=pack
                )
                with (
                    patch.dict(sys.modules, {"aethron_vision_native": native}),
                    patch.object(self.np, "ascontiguousarray") as portable,
                ):
                    expected = RuntimeError if type(version) is int and version == 1 else ValueError
                    with self.assertRaises(expected) as raised:
                        self.detector.infer(pixels, lighting="daylight")
                portable.assert_not_called()
                self.assertEqual(self.inputs, [])
                if expected is RuntimeError:
                    self.assertIs(raised.exception, error)
                    self.assertEqual(pack.call_count, 1)
                else:
                    pack.assert_not_called()

    def test_broken_dependency_does_not_select_portable_packing(self):
        import builtins

        original_import = builtins.__import__
        error = ModuleNotFoundError("missing_native_dependency", name="native_dependency")

        def broken_import(name, *args, **kwargs):
            if name == "aethron_vision_native":
                raise error
            return original_import(name, *args, **kwargs)

        with (
            patch.object(builtins, "__import__", side_effect=broken_import),
            patch.object(self.np, "ascontiguousarray") as portable,
        ):
            with self.assertRaises(ModuleNotFoundError) as raised:
                self.detector.infer(
                    self.np.zeros((64, 64, 3), dtype=self.np.uint8), lighting="daylight"
                )
        self.assertIs(raised.exception, error)
        portable.assert_not_called()
        self.assertEqual(self.inputs, [])

    def test_native_dispatch_uses_original_canvas_and_owned_output(self):
        canvas = self.np.zeros((640, 640, 3), dtype=self.np.uint8)
        outputs = []

        def pack(source, output):
            self.assertIs(source, canvas)
            self.assertEqual(output.shape, (1, 3, 640, 640))
            self.assertEqual(output.dtype, self.np.float32)
            self.assertTrue(output.flags.c_contiguous)
            self.assertFalse(self.np.shares_memory(source, output))
            output.fill(19)
            outputs.append(output)
            return True

        native = SimpleNamespace(CONTRACT_VERSION=1, PACK_CONTRACT_VERSION=1, pack_rgb=pack)
        with patch.dict(sys.modules, {"aethron_vision_native": native}):
            actual = _packed_rgb(canvas)
        self.assertEqual(len(outputs), 1)
        self.assertIs(actual, outputs[0])
        self.assertTrue((actual == 19).all())
