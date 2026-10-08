import importlib.util
import json
import random
import unittest


def observation(sensor="thermal", values=None, **kw):
    out = {
        "sensor": sensor,
        "zone": "near",
        "at_ms": 1000,
        "calibration_until_ms": 2000,
        "quality": "valid",
        "values": values if values is not None else [80],
        "inference_ms": 10,
        "nonhuman": False,
        "rect": None,
    }
    out.update(kw)
    return out


def request(*obs, **kw):
    out = {
        "version": 1,
        "now_ms": 1000,
        "clock": "monotonic",
        "lighting": "daylight",
        "evidence": "synthetic",
        "authorized_obstruction": False,
        "contract": "warn",
        "zones": ["near"],
        "observations": list(obs),
    }
    out.update(kw)
    return out


def evaluate(doc):
    assert importlib.util.find_spec("aethron.core") is not None, "bounded runtime missing"
    from aethron.core import evaluate as run

    return run(json.dumps(doc).encode())


def claim(result, cap="thermal_source", zone="near"):
    return next(c for c in result["claims"] if c["capability"] == cap and c["zone"] == zone)


class CoreTests(unittest.TestCase):
    def test_thermal_zero_visible_without_rgb(self):
        c = claim(evaluate(request(observation(), lighting="zero_visible")))
        self.assertEqual((c["state"], c["kind"]), ("PRESENT", "hot"))
        self.assertIsNone(c["rect"])

    def test_thermal_classes(self):
        for values, state, kind in [
            ([160], "PRESENT", "fire_like"),
            ([-5], "PRESENT", "cold"),
            ([20], "ABSENT", "none"),
        ]:
            c = claim(evaluate(request(observation(values=values))))
            self.assertEqual((c["state"], c["kind"]), (state, kind))

    def test_darkness_camera_and_passive_withdraw(self):
        for light in ["daylight", "low_light", "near_dark", "zero_visible"]:
            out = evaluate(
                request(
                    observation("rgb", [0.95]), observation("depth_passive", [1]), lighting=light
                )
            )
            for cap in ["human_presence", "obstacle"]:
                self.assertEqual(
                    claim(out, cap)["state"], "PRESENT" if light == "daylight" else "UNKNOWN"
                )
            self.assertIsNone(claim(out, "human_presence")["rect"])

    def test_active_depth_darkness_and_zero_invalid(self):
        for values, state in [([1], "PRESENT"), ([3], "ABSENT"), ([0, 3], "UNKNOWN")]:
            self.assertEqual(
                claim(
                    evaluate(request(observation("depth_active", values), lighting="zero_visible")),
                    "obstacle",
                )["state"],
                state,
            )

    def test_radar_coarse_authorized_fallback(self):
        doc = request(
            observation("radar", [0.95], zone="sector_a"),
            zones=["sector_a"],
            authorized_obstruction=True,
            lighting="zero_visible",
        )
        out = evaluate(doc)
        self.assertEqual(claim(out, "occupancy_zone", "sector_a")["state"], "PRESENT")
        self.assertEqual(claim(out, "human_presence", "sector_a")["state"], "UNKNOWN")
        self.assertIsNone(claim(out, "occupancy_zone", "sector_a")["rect"])
        doc["authorized_obstruction"] = False
        with self.assertRaises(ValueError):
            evaluate(doc)

    def test_missing_sensors_fail_safe(self):
        out = evaluate(request(lighting="zero_visible", contract="vehicle_stop"))
        self.assertTrue(all(c["state"] == "UNKNOWN" for c in out["claims"]))
        self.assertEqual(out["recommendation"]["action"], "STOP")
        self.assertTrue(out["degraded"])

    def test_invalid_quality_withdraws_and_explains(self):
        for quality in [
            "dark",
            "saturated",
            "occluded",
            "noisy",
            "multipath",
            "dropped",
            "model_error",
        ]:
            c = claim(evaluate(request(observation(quality=quality))))
            self.assertEqual(c["state"], "UNKNOWN")
            self.assertIn(quality, c["reasons"])

    def test_timing_and_calibration_boundaries(self):
        for kw, reason in [
            ({"at_ms": 499}, "stale"),
            ({"at_ms": 1001}, "future"),
            ({"calibration_until_ms": 999}, "calibration"),
            ({"inference_ms": 101}, "timeout"),
        ]:
            c = claim(evaluate(request(observation(**kw))))
            self.assertEqual(c["state"], "UNKNOWN")
            self.assertIn(reason, c["reasons"])
        self.assertEqual(claim(evaluate(request(observation(at_ms=500))))["state"], "PRESENT")

    def test_disagreement_and_skew(self):
        for aux, reason in [
            (observation("thermal_aux", [20]), "disagreement"),
            (observation("thermal_aux", [80], at_ms=899), "skew"),
        ]:
            out = evaluate(request(observation(), aux, lighting="zero_visible"))
            self.assertEqual(claim(out)["state"], "UNKNOWN")
            self.assertIn(reason, claim(out)["reasons"])
            self.assertIsNone(claim(out)["rect"])

    def test_single_healthy_sensor_survives_invalid_peer(self):
        out = evaluate(request(observation(), observation("thermal_aux", [80], quality="dropped")))
        self.assertEqual(claim(out)["state"], "PRESENT")
        self.assertTrue(out["degraded"])
        self.assertIn("dropped", claim(out)["reasons"])

    def test_rect_requires_fresh_nonhuman_direct_evidence(self):
        obs = observation(nonhuman=True, rect=[10, 20, 30, 40])
        self.assertEqual(claim(evaluate(request(obs)))["rect"], [10, 20, 30, 40])
        for kw in [{"at_ms": 0}, {"quality": "occluded"}]:
            other = dict(obs, **kw)
            self.assertIsNone(claim(evaluate(request(other)))["rect"])
        obs["nonhuman"] = False
        with self.assertRaises(ValueError):
            evaluate(request(obs))

    def test_no_geometry_for_people_or_radar_or_behind_barrier(self):
        for sensor, zone, vals in [
            ("rgb", "near", [0.9]),
            ("radar", "sector_a", [0.9]),
            ("thermal", "sector_a", [80]),
        ]:
            with self.assertRaises(ValueError):
                evaluate(
                    request(
                        observation(sensor, vals, zone=zone, nonhuman=True, rect=[0, 0, 10, 10]),
                        zones=[zone],
                        authorized_obstruction=True,
                    )
                )

    def test_geometry_consensus_required(self):
        out = evaluate(
            request(
                observation(nonhuman=True, rect=[0, 0, 10, 10]), observation("thermal_aux", [80])
            )
        )
        self.assertEqual(claim(out)["state"], "PRESENT")
        self.assertIsNone(claim(out)["rect"])

    def test_cue_uncertainty_and_absence(self):
        for score, state in [
            (0, "ABSENT"),
            (0.2, "ABSENT"),
            (0.21, "UNKNOWN"),
            (0.79, "UNKNOWN"),
            (0.8, "PRESENT"),
            (1, "PRESENT"),
        ]:
            out = evaluate(request(observation("rgb", [score])))
            self.assertEqual(claim(out, "human_presence")["state"], state)

    def test_contracts_are_bounded_recommendations(self):
        for contract, action in [
            ("warn", "WARN"),
            ("vehicle_stop", "STOP"),
            ("drone_hover", "HOVER"),
            ("drone_land", "LAND"),
            ("drone_retreat", "RETREAT"),
        ]:
            out = evaluate(request(contract=contract))
            self.assertEqual(out["recommendation"]["action"], action)
            self.assertTrue(out["recommendation"]["requires_independent_controller"])
            self.assertLessEqual(out["valid_until_ms"], 1200)
        with self.assertRaises(ValueError):
            evaluate(request(contract="pursue"))

    def test_no_arbitrary_metadata_or_identity(self):
        for key in ["person_id", "track", "name", "trajectory", "raw", "face", "voice"]:
            doc = request(observation())
            doc["observations"][0][key] = "sensitive"
            with self.assertRaises(ValueError):
                evaluate(doc)
        out = evaluate(request(observation("rgb", [0.95])))
        self.assertNotIn("person_id", json.dumps(out))
        self.assertEqual(evaluate(request()), evaluate(request()))

    def test_numeric_and_resource_rejection(self):
        for value in [True, "80", float("inf"), float("nan"), 1001, -101]:
            with self.assertRaises(ValueError):
                evaluate(request(observation(values=[value])))
        for doc in [
            request(observation(values=[80] * 257)),
            request(*[observation()] * 29),
            request(observation(), observation()),
            request(version=True),
            request(now_ms=-1),
            request(clock="wall"),
            request(evidence="live"),
            request(zones=["near", "near"]),
        ]:
            with self.assertRaises(ValueError):
                evaluate(doc)

    def test_parser_malformed(self):
        from aethron.core import evaluate as run

        for data in [
            b'{"version":1,"version":1}',
            b"[" * 1000,
            b" " * 65537,
            b"null",
            b"\xff",
            b"{} trailing",
        ]:
            with self.assertRaises(ValueError):
                run(data)

    def test_model_tamper_is_fail_closed(self):
        from aethron.core import evaluate as run

        out = run(json.dumps(request(observation())).encode(), model_bytes=b"{}")
        self.assertEqual(claim(out)["state"], "UNKNOWN")
        self.assertIn("model_error", claim(out)["reasons"])

    def test_generated_reference_permutation_and_withdrawal(self):
        rng = random.Random(8871)
        for _ in range(2400):
            a, b = rng.choice([20, 80, 180]), rng.choice([20, 80, 180])
            # Independent truth table, no production helper reuse.
            table = {20: ("ABSENT", "none"), 80: ("PRESENT", "hot"), 180: ("PRESENT", "fire_like")}
            expected = table[a] if a == b else ("UNKNOWN", "none")
            obs = [observation(values=[a]), observation("thermal_aux", [b])]
            out = evaluate(request(*obs, lighting=rng.choice(["daylight", "zero_visible"])))
            c = claim(out)
            self.assertEqual((c["state"], c["kind"]), expected)
            reverse = evaluate(request(*reversed(obs), lighting=out["lighting"]))
            self.assertEqual(out, reverse)
            invalid = [dict(o, quality="dropped") for o in obs]
            self.assertEqual(claim(evaluate(request(*invalid)))["state"], "UNKNOWN")
            self.assertNotIn("SAFE", json.dumps(out))


if __name__ == "__main__":
    unittest.main()
