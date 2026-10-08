import json
import unittest

from test_core import claim, evaluate, observation, request


def person(sensor="rgb", **kw):
    return observation(sensor, [0.95], rect=[20, 20, 30, 50], **kw)


def scene(*obs, **kw):
    return request(*obs, version=2, mode="direct", contract="vehicle_stop", **kw)


class V2Tests(unittest.TestCase):
    def test_1_person_survives_rgb_blackout(self):
        for sensor in ["thermal_person", "depth_person"]:
            day = evaluate(scene(person(), person(sensor)))
            night = evaluate(scene(person(), person(sensor), lighting="zero_visible"))
            self.assertEqual(claim(day, "human_presence")["rect"], [20, 20, 30, 50])
            self.assertEqual(claim(night, "human_presence")["rect"], [20, 20, 30, 50])
            self.assertEqual(claim(night, "human_presence")["state"], "PRESENT")

    def test_2_support_provenance_withdraws_rgb(self):
        out = evaluate(scene(person(), person("thermal_person"), lighting="zero_visible"))
        self.assertEqual(claim(out, "human_presence")["sources"], ["thermal_person"])
        self.assertIn("darkness", claim(out, "human_presence")["reasons"])

    def test_3_confidence_degrades(self):
        a = claim(evaluate(scene(person(), person("thermal_person"))), "human_presence")
        b = claim(
            evaluate(scene(person(), person("thermal_person"), lighting="zero_visible")),
            "human_presence",
        )
        self.assertEqual(a["confidence"], "high")
        self.assertEqual(b["confidence"], "medium")
        self.assertEqual(b["confidence_semantics"], "uncalibrated_score")

    def test_4_expiry_has_no_reusable_identity(self):
        from rescuesense.render import render

        doc = scene(person("thermal_person"))
        self.assertLessEqual(evaluate(doc)["valid_until_ms"], 1200)
        doc["now_ms"] = 1501
        c = claim(evaluate(doc), "human_presence")
        self.assertEqual(c["state"], "UNKNOWN")
        self.assertIsNone(c["rect"])
        self.assertNotIn("data-detection", render(json.dumps(doc).encode(), 1501))
        self.assertFalse(any("id" == k or "track" in k or "association" in k for k in c))

    def test_5_no_reidentification_after_reentry(self):
        before = evaluate(scene(person("thermal_person")))
        gone = evaluate(scene(lighting="zero_visible"))
        after = evaluate(scene(person("thermal_person")))
        self.assertEqual(before, after)
        self.assertEqual(claim(gone, "human_presence")["state"], "UNKNOWN")
        for field in ["person_id", "track_id", "association_id", "history", "velocity"]:
            obs = person("thermal_person")
            obs[field] = "reused"
            with self.assertRaises(ValueError):
                evaluate(scene(obs))

    def test_6_all_sensor_loss_unknown_failsafe(self):
        for contract, action in [("vehicle_stop", "STOP"), ("drone_hover", "HOVER")]:
            doc = scene(
                person(), person("thermal_person", quality="dropped"), lighting="zero_visible"
            )
            doc["contract"] = contract
            out = evaluate(doc)
            c = claim(out, "human_presence")
            self.assertEqual(c["state"], "UNKNOWN")
            self.assertIsNone(c["rect"])
            self.assertEqual(c["sources"], [])
            self.assertEqual(out["recommendation"]["action"], action)

    def test_7_through_wall_never_human_boxes(self):
        doc = request(
            observation("radar", [0.95], zone="sector_a"),
            version=2,
            mode="through_obstruction",
            zones=["sector_a"],
            authorized_obstruction=True,
            lighting="zero_visible",
        )
        out = evaluate(doc)
        self.assertEqual(claim(out, "occupancy_zone", "sector_a")["state"], "PRESENT")
        self.assertTrue(all(c["rect"] is None for c in out["claims"]))
        for sensor in ["rgb", "thermal_person", "depth_person"]:
            bad = scene(person(sensor))
            bad.update(mode="through_obstruction", authorized_obstruction=True)
            with self.assertRaises(ValueError):
                evaluate(bad)
        doc["observations"][0]["rect"] = [1, 1, 10, 10]
        with self.assertRaises(ValueError):
            evaluate(doc)
