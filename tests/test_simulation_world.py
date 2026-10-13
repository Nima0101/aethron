import json
import unittest

from aethron.simulation_world import SimulatedWorld
from aethron.temporal.fixtures import detection, encode, frame, sensor
from aethron.world import CLOCK_DOMAIN, COORDINATE_FRAME


class SimulationWorld(unittest.TestCase):
    def setUp(self):
        self.model = SimulatedWorld("vehicle_stop")

    def step(self, f, **changes):
        options = {
            "now_ms": f["at_ms"],
            "coordinate_frame": COORDINATE_FRAME,
            "clock_domain": CLOCK_DOMAIN,
        }
        options.update(changes)
        return self.model.step(encode(f), **options)

    def test_current_synthetic_support_exports_only_aggregate(self):
        out = self.step(frame(0, [detection()]))
        self.assertEqual(
            set(out), {"simulation_world_version", "quarantined", "diagnostics", "recommendation"}
        )
        self.assertEqual(out["simulation_world_version"], 1)
        self.assertFalse(out["quarantined"])
        rec = out["recommendation"]
        self.assertTrue(rec["accepted"])
        self.assertEqual(rec["state"], "PRESENT")
        self.assertEqual(rec["action"], "STOP")
        self.assertTrue(rec["simulation_only"])
        self.assertFalse(rec["motion_authority"])
        for key in ('"id"', '"box"', '"tracks"', '"prediction"', '"range_m"'):
            self.assertNotIn(key, json.dumps(out))

    def test_original_frame_time_caps_processing_delayed_expiry(self):
        out = self.step(frame(0, [detection()]), now_ms=90)["recommendation"]
        self.assertTrue(out["accepted"])
        self.assertEqual(out["at_ms"], 90)
        self.assertEqual(out["expires_at_ms"], 100)

    def test_sensor_and_calibration_deadlines_are_not_extended(self):
        f = frame(90, [detection()])
        f["sensors"][0]["at_ms"] = 0
        out = self.step(f, now_ms=95)["recommendation"]
        self.assertEqual(out["expires_at_ms"], 100)
        self.model = SimulatedWorld("vehicle_stop")
        f["sensors"][0]["calibration_until_ms"] = 97
        self.assertEqual(self.step(f, now_ms=95)["recommendation"]["expires_at_ms"], 97)

    def test_dark_rgb_keeps_thermal_support_and_negative_diagnostic(self):
        f = frame(0, [detection()], lighting="zero_visible")
        f["sensors"].append(sensor(0, [], kind="rgb", quality="dark"))
        out = self.step(f)
        self.assertEqual(out["recommendation"]["state"], "PRESENT")
        self.assertIn("rgb:dark", out["diagnostics"])
        lost = self.model.watchdog(now_ms=1)
        self.assertIn("rgb:dark", lost["diagnostics"])
        self.assertEqual(lost["recommendation"]["state"], "UNKNOWN")
        self.assertEqual(lost["recommendation"]["expires_at_ms"], 1)

    def test_prediction_and_empty_scene_never_become_present(self):
        self.step(frame(0, [detection()]))
        self.step(frame(50, [detection(0.11)]))
        out = self.step(frame(100, []))["recommendation"]
        self.assertEqual(out["state"], "UNKNOWN")
        self.assertEqual(out["action"], "STOP")
        self.assertFalse(out["motion_authority"])
        self.assertEqual(self.step(frame(700, []))["recommendation"]["state"], "UNKNOWN")

    def test_non_synthetic_or_changed_policy_quarantines_before_world(self):
        for key, value in (
            ("evidence", "recorded"),
            ("evidence", "external_unverified"),
            ("contract", "drone_land"),
        ):
            with self.subTest(key=key, value=value):
                self.model = SimulatedWorld("vehicle_stop")
                self.step(frame(0, [detection()]))
                f = frame(100, [detection()])
                f[key] = value
                out = self.step(f)
                self.assertTrue(out["quarantined"])
                self.assertFalse(out["recommendation"]["accepted"])
                self.assertIsNone(out["recommendation"]["evidence"])
                self.assertEqual(out["recommendation"]["action"], "STOP")
                self.assertEqual(
                    self.step(frame(101, [detection()]))["recommendation"]["state"], "PRESENT"
                )

    def test_unsupported_context_and_invalid_clocks_fail_closed(self):
        for changes in (
            {"coordinate_frame": "secret-map"},
            {"clock_domain": "secret-clock"},
            {"now_ms": True},
            {"now_ms": -1},
        ):
            self.model = SimulatedWorld("vehicle_stop")
            out = self.step(frame(0, [detection()]), **changes)
            self.assertTrue(out["quarantined"])
            self.assertFalse(out["recommendation"]["accepted"])
            self.assertNotIn("secret", json.dumps(out))

    def test_both_watermarks_survive_faults_and_watchdog(self):
        self.step(frame(100, [detection()]))
        self.model.watchdog(now_ms=150)
        self.assertTrue(self.step(frame(140, [detection()]))["quarantined"])
        self.assertTrue(self.step(frame(100, [detection()]), now_ms=150)["quarantined"])
        self.assertTrue(self.step(frame(151, [detection()]))["recommendation"]["accepted"])

    def test_exact_support_expiry_is_conservatively_rejected(self):
        out = self.step(frame(0, [detection()]), now_ms=100)["recommendation"]
        self.assertFalse(out["accepted"])
        self.assertEqual(out["state"], "UNKNOWN")
        self.assertEqual(out["expires_at_ms"], 100)

    def test_malformed_input_clears_support_without_echo(self):
        for bad in (
            b'{"secret":"content"}',
            b'{"version":3,"version":3}',
            b"[" * 9,
            b"x" * 65537,
            {},
            b"\xff",
        ):
            self.step(frame(0, [detection()]))
            out = self.model.step(
                bad, now_ms=1, coordinate_frame=COORDINATE_FRAME, clock_domain=CLOCK_DOMAIN
            )
            self.assertTrue(out["quarantined"])
            self.assertEqual(out["recommendation"]["state"], "UNKNOWN")
            self.assertNotIn("content", json.dumps(out))
            self.model = SimulatedWorld("vehicle_stop")

    def test_close_is_terminal_and_outputs_do_not_alias(self):
        out = self.step(frame(0, [detection()]))
        out["diagnostics"].append("private-marker")
        out["recommendation"]["reasons"].append("private-marker")
        self.assertNotIn("private-marker", json.dumps(self.model.watchdog(now_ms=1)))
        self.model.close()
        self.model.close()
        out = self.step(frame(2, [detection()]))
        self.assertTrue(out["quarantined"])
        self.assertFalse(out["recommendation"]["accepted"])
        self.assertIn("closed", out["diagnostics"])


if __name__ == "__main__":
    unittest.main()
