import tempfile
import unittest
from pathlib import Path

from aethron.vision.yolox import RGBDetector, safe_class


class VisionBoundary(unittest.TestCase):
    def test_model_tamper_rejected_before_native_import(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.onnx"
            path.write_bytes(b"not a trusted model")
            with self.assertRaises(ValueError):
                RGBDetector(path)

    def test_class_mapping_never_invents_uav_or_cyclist(self):
        self.assertEqual(safe_class(0), "person")
        self.assertEqual(safe_class(4), "obstacle")
        self.assertEqual(safe_class(1), "equipment")
        self.assertNotIn("uav", [safe_class(i) for i in range(80)])
        self.assertNotIn("cyclist", [safe_class(i) for i in range(80)])
        self.assertIsNone(safe_class(79))
