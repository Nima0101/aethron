import unittest
from pathlib import Path

from aethron_edge.pixel_replay import replay_images

ROOT = Path(__file__).resolve().parents[2]


class PixelReplay(unittest.TestCase):
    def test_licensed_pixels_detector_registration_and_core_without_labels(self):
        report = replay_images(
            [ROOT / "data/rgb-smoke/person.png"] * 2, ROOT / "build/models/yolox.onnx"
        )
        self.assertEqual(report.frame_count, 2)
        self.assertEqual(report.runtime_mode, "replay")
        self.assertTrue(all(r.evidence == "recorded" for r in report.results))
        self.assertTrue(any(t.class_ == "person" for r in report.results for t in r.tracks))
        self.assertTrue(all(t.sources == ["rgb"] for r in report.results for t in r.tracks))
