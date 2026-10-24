import json
import unittest

from aethron.schema import MAX_TIME
from aethron.temporal.fixtures import detection, encode, frame, sensor
from aethron.world import WorldModel


class WorldBoundary(unittest.TestCase):
    def setUp(self):
        self.world = WorldModel()

    def step(self, f, **kwargs):
        options = {
            "now_ms": f["at_ms"],
            "coordinate_frame": "registered_image_normalized",
            "clock_domain": "host_monotonic_ms",
        }
        options.update(kwargs)
        return self.world.step(encode(f), **options)

    def assert_quarantined(self, out, reason):
        self.assertTrue(out["quarantined"])
        self.assertEqual(out["scene"]["state"], "UNKNOWN")
        self.assertEqual(out["scene"]["tracks"], [])
        self.assertIsNone(out["scene"]["evidence"])
        self.assertIn(reason, out["scene"]["reasons"])
        self.assertEqual(out["scene"]["expires_at_ms"], out["scene"]["at_ms"])

    def test_context_quarantine_clears_linkage_without_echo(self):
        for key, values in (
            ("coordinate_frame", ("map", "odom", "private-camera", None, [])),
            ("clock_domain", ("ros_time", "unix_ms", "private-clock", True, {})),
        ):
            for value in values:
                with self.subTest(key=key, value=value):
                    self.world = WorldModel()
                    first = self.step(frame(0, [detection()]))["scene"]["tracks"][0]["id"]
                    out = self.step(frame(100, [detection()]), **{key: value})
                    self.assert_quarantined(out, "unsupported_" + key)
                    self.assertNotIn("private-", json.dumps(out))
                    self.assertEqual(out["scene"]["recommendation"]["action"], "STOP")
                    out = self.step(frame(200, [detection()]))
                    self.assertFalse(out["quarantined"])
                    self.assertNotEqual(first, out["scene"]["tracks"][0]["id"])

    def test_clock_watermark_survives_watchdog_and_quarantine(self):
        self.step(frame(0, [detection()]))
        self.world.watchdog(now_ms=200)
        self.assert_quarantined(self.step(frame(100, [detection()])), "clock_regression")
        self.assert_quarantined(self.step(frame(150, [detection()])), "clock_regression")
        self.assertFalse(self.step(frame(201, [detection()]))["quarantined"])

    def test_frame_watermark_survives_errors_and_scene_break(self):
        f = frame(100, [detection()])
        self.step(f)
        bad = frame(110, [detection()])
        bad["private-field"] = "private-content"
        self.assert_quarantined(self.step(bad), "invalid_input")
        f["scene_break"] = True
        out = self.step(f, now_ms=120)
        self.assert_quarantined(out, "frame_regression")
        self.assertNotIn("private-", json.dumps(out))
        self.assertFalse(self.step(frame(130, [detection()]))["quarantined"])

    def test_stale_and_future_frames_do_not_poison_frame_watermark(self):
        for at in (0, 1000):
            with self.subTest(at=at):
                self.world = WorldModel()
                self.assert_quarantined(
                    self.step(frame(at, [detection()]), now_ms=200), "frame_timestamp"
                )
                self.assertFalse(self.step(frame(200, [detection()]))["quarantined"])

    def test_invalid_clocks_are_bounded_and_do_not_echo(self):
        for bad in (True, -1, MAX_TIME + 1, float("nan"), float("inf"), "secret", None):
            with self.subTest(bad=bad):
                self.world = WorldModel()
                self.step(frame(50, [detection()]))
                out = self.world.watchdog(now_ms=bad)
                self.assert_quarantined(out, "invalid_clock")
                self.assertEqual(out["scene"]["at_ms"], 50)
                self.assertNotIn("secret", json.dumps(out, allow_nan=False))

    def test_watchdog_preserves_negative_evidence_and_withdraws_support(self):
        f = frame(0, [detection()], kind="depth")
        f["sensors"].append(sensor(0, [], "rgb", "dark"))
        self.step(f)
        out = self.world.watchdog(now_ms=1)
        self.assertFalse(out["quarantined"])
        scene = out["scene"]
        self.assertEqual(scene["state"], "UNKNOWN")
        self.assertIn("rgb:dark", scene["reasons"])
        self.assertIn("acquisition_stalled", scene["reasons"])
        self.assertEqual(scene["tracks"][0]["sources"], [])
        self.assertIsNone(scene["tracks"][0]["range_m"])
        self.assertEqual(self.world.watchdog(now_ms=501)["scene"]["tracks"], [])

    def test_quarantine_is_sticky_until_valid_step(self):
        self.assert_quarantined(
            self.step(frame(0, []), clock_domain="unix_ms"), "unsupported_clock_domain"
        )
        self.assert_quarantined(self.world.watchdog(now_ms=1), "unsupported_clock_domain")
        out = self.step(frame(2, []))
        self.assertFalse(out["quarantined"])
        self.assertNotIn("unsupported_clock_domain", out["scene"]["reasons"])

    def test_quarantine_keeps_known_negative_evidence_bounded(self):
        f = frame(100, [], kind="rgb")
        f["sensors"][0]["quality"] = "dark"
        self.step(f)
        self.step(frame(110, []), coordinate_frame="map")
        out = self.world.watchdog(now_ms=109)
        self.assert_quarantined(out, "clock_regression")
        self.assertIn("rgb:dark", out["scene"]["reasons"])
        self.assertIn("unsupported_coordinate_frame", out["scene"]["reasons"])
        for _ in range(20):
            later = self.world.watchdog(now_ms=109)
        self.assertEqual(later["scene"]["reasons"], out["scene"]["reasons"])
        self.assertEqual(self.step(frame(120, []))["scene"]["reasons"], [])

    def test_returned_objects_cannot_mutate_future_output(self):
        out = self.step(frame(0, [detection()]))
        out["scene"]["tracks"][0]["box"][0] = 0.99
        out["scene"]["recommendation"]["action"] = "arbitrary"
        out["scene"]["reasons"].append("private-marker")
        later = self.world.watchdog(now_ms=1)
        self.assertNotIn("private-marker", json.dumps(later))
        self.assertAlmostEqual(later["scene"]["tracks"][0]["box"][0], 0.1)
        self.assertEqual(later["scene"]["recommendation"]["action"], "STOP")

    def test_close_is_terminal(self):
        self.step(frame(0, [detection()]))
        self.world.close()
        self.world.close()
        self.assert_quarantined(self.step(frame(100, [detection()])), "closed")
        self.assert_quarantined(self.world.watchdog(now_ms=200), "closed")

    def test_no_identity_or_obstruction_extensions(self):
        for field in ("person_id", "embedding", "history", "target", "camera_id"):
            self.world = WorldModel()
            f = frame(0, [detection()])
            f["sensors"][0]["detections"][0][field] = "private-content"
            out = self.step(f)
            self.assert_quarantined(out, "invalid_input")
            self.assertNotIn("private-content", json.dumps(out))
        f = frame(1, [detection()])
        f["mode"] = "through_obstruction"
        self.assert_quarantined(self.step(f), "invalid_input")


if __name__ == "__main__":
    unittest.main()
