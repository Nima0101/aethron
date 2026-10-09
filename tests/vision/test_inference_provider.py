"""Provider loss must not turn explicit Core ML selection into CPU-only success."""

import unittest

from aethron.vision.yolox import RGBDetector


class InferenceProvider(unittest.TestCase):
    def detector(self, *, lost_before=False, lost_during=False):
        import cv2
        import numpy as np

        class NativeSession:
            # The boundary reproduces ORT's documented provider fallback. Pixel
            # preparation, provider admission and output validation stay real.
            lost = lost_before

            def get_providers(self):
                return (
                    ["CPUExecutionProvider"]
                    if self.lost
                    else ["CoreMLExecutionProvider", "CPUExecutionProvider"]
                )

            def run(self, outputs, inputs):
                self.lost = lost_during or self.lost
                return [np.zeros((1, 8400, 85), dtype=np.float32)]

        detector = RGBDetector.__new__(RGBDetector)
        detector.np, detector.cv = np, cv2
        detector.backend = "coreml"
        detector.ort_input_name = "input"
        detector.ort_session = NativeSession()
        return detector, np.zeros((2, 2, 3), dtype=np.uint8)

    def test_missing_selected_provider_rejects_inference(self):
        detector, pixels = self.detector(lost_before=True)
        with self.assertRaises(ValueError):
            detector.infer(pixels, lighting="daylight")

    def test_provider_fallback_during_run_rejects_cpu_only_result(self):
        detector, pixels = self.detector(lost_during=True)
        with self.assertRaises(ValueError):
            detector.infer(pixels, lighting="daylight")

    def test_available_provider_keeps_empty_output_and_darkness_suppression(self):
        detector, pixels = self.detector()
        self.assertEqual(detector.infer(pixels, lighting="daylight"), [])
        self.assertEqual(detector.infer(pixels, lighting="zero_visible"), [])
