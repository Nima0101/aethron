import time
import unittest
from pathlib import Path

from aethron_edge.config import Profile
from aethron_edge.pipeline import RuntimePipeline

ROOT = Path(__file__).resolve().parents[2]


class Pipeline(unittest.TestCase):
    def test_headless_replay_expires_when_worker_stops(self):
        pipeline = RuntimePipeline(
            Profile(
                name="bench",
                driver="replay",
                address=str(ROOT / "examples/temporal-blackout.jsonl"),
            )
        )
        pipeline.start()
        try:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                result = pipeline.tick(time.monotonic_ns())
                if result["state"] == "PRESENT":
                    break
                time.sleep(0.01)
            self.assertEqual(result["state"], "PRESENT")
            self.assertEqual(result["evidence"], "synthetic")
            pipeline.stop_worker()
            time.sleep(0.15)
            self.assertEqual(pipeline.tick(time.monotonic_ns())["state"], "UNKNOWN")
        finally:
            pipeline.close()

    def test_real_pixels_detector_keeps_untrusted_capture_unknown(self):
        import tempfile

        import cv2

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "person.avi"
            image = cv2.imread(str(ROOT / "data/rgb-smoke/person.png"))
            image = cv2.resize(image, (640, 480))
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (640, 480))
            for _ in range(20):
                writer.write(image)
            writer.release()
            p = RuntimePipeline(
                Profile(
                    name="pixels",
                    driver="file",
                    address=str(path),
                    model=str(ROOT / "build/models/yolox.onnx"),
                )
            )
            p.start()
            try:
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline and p.processed == 0:
                    p.tick(time.monotonic_ns())
                    time.sleep(0.02)
                self.assertGreater(p.processed, 0)
                self.assertEqual(p.snapshot(time.monotonic_ns())["state"], "UNKNOWN")
                self.assertEqual(p.reason, "clock_untrusted")
            finally:
                p.close()
