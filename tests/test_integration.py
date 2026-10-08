import json
import os
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

from test_core import observation, request


class IntegrationTests(unittest.TestCase):
    def test_cli_bounded_error_and_evaluation(self):
        p = subprocess.run(
            [sys.executable, "-m", "aethron", "evaluate", "-"],
            input=json.dumps(request(observation())).encode(),
            capture_output=True,
            check=False,
        )
        self.assertEqual(p.returncode, 0, p.stderr.decode())
        self.assertEqual(json.loads(p.stdout)["claims"][2]["kind"], "hot")
        p = subprocess.run(
            [sys.executable, "-m", "aethron", "evaluate", "-"],
            input=b'{"secret":"private"}',
            capture_output=True,
            check=False,
        )
        self.assertEqual(p.returncode, 2)
        self.assertNotIn(b"private", p.stdout + p.stderr)

    def test_cli_svg_is_utf8_even_when_console_encoding_is_ascii(self):
        doc = request(observation(nonhuman=True, rect=[10, 20, 30, 40]))
        p = subprocess.run(
            [sys.executable, "-m", "aethron", "render", "-", "--now-ms", "1000"],
            input=json.dumps(doc).encode(),
            capture_output=True,
            check=False,
            env=dict(os.environ, PYTHONIOENCODING="ascii"),
        )
        self.assertEqual(p.returncode, 0, p.stderr.decode())
        root = ET.fromstring(p.stdout.decode("utf-8"))
        self.assertEqual(
            len(root.findall(".//{http://www.w3.org/2000/svg}rect[@data-detection]")), 1
        )

    def test_renderer_expires_rectangles_and_never_draws_people(self):
        from aethron.render import render

        data = json.dumps(
            request(observation(nonhuman=True, rect=[10, 20, 30, 40]), observation("rgb", [0.95]))
        ).encode()
        root = ET.fromstring(render(data, 1000))
        boxes = root.findall(".//{http://www.w3.org/2000/svg}rect[@data-detection]")
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0].attrib["data-detection"], "hot")
        self.assertIn("human_presence: PRESENT", render(data, 1000))
        self.assertNotIn("data-detection", render(data, 1501))
        self.assertIn("UNKNOWN", render(data, 1501))
        with self.assertRaises(ValueError):
            render(data, 999)

    def test_adapter_minimizes_patch_to_nonhuman_box(self):
        from aethron.adapters import coarse_cue, depth_patch, thermal_patch

        a = thermal_patch(
            [80, 90], at_ms=1000, calibration_until_ms=2000, rect=[0, 0, 20, 20], nonhuman=True
        )
        self.assertEqual(a["rect"], [0, 0, 20, 20])
        b = depth_patch([1], at_ms=1000, calibration_until_ms=2000)
        self.assertEqual(b["sensor"], "depth_active")
        c = coarse_cue("radar", 0.9, zone="sector_a", at_ms=1000, calibration_until_ms=2000)
        self.assertIsNone(c["rect"])
        for func, values in [(thermal_patch, [2000]), (depth_patch, [float("nan")])]:
            with self.assertRaises(ValueError):
                func(values, at_ms=1000, calibration_until_ms=2000)
        with self.assertRaises(ValueError):
            coarse_cue("face", 0.9, zone="near", at_ms=1000, calibration_until_ms=2000)

    def test_demo_cases_have_expected_failure_behavior(self):
        p = subprocess.run(
            [sys.executable, "-m", "aethron", "demo"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = [json.loads(line) for line in p.stdout.splitlines()]
        cases = {row["scenario"]: row["result"] for row in rows}
        self.assertIn("zero-visible-thermal", cases)
        self.assertIn("darkness-disagreement", cases)
        self.assertIn("stale-rectangle", cases)
        self.assertTrue(all(row["evidence"] == "synthetic" for row in cases.values()))


if __name__ == "__main__":
    unittest.main()
