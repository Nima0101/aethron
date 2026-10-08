import io
import itertools
import json
import math
import random
import unittest

from rescuesense import evaluate
from rescuesense.schema import parse
from rescuesense.temporal import Session
from rescuesense.temporal.fixtures import detection, encode, frame, sensor, sequences
from rescuesense.temporal.math import Axis, assignment, translation
from rescuesense.temporal.pixels import detect_pgm
from rescuesense.temporal.replay import replay


class Temporal(unittest.TestCase):
    def setUp(self):
        self.s = Session()

    def step(self, f):
        return self.s.step(encode(f), now_ms=f["at_ms"])

    def test_blackout_three_nonvisible_supports(self):
        out = [self.step(x["frame"]) for x in sequences()["blackout"]]
        self.assertEqual(len({x["tracks"][0]["id"] for x in out}), 1)
        self.assertEqual(out[-1]["tracks"][0]["sources"], ["depth", "lwir", "radar"])
        self.assertIsNotNone(out[-1]["tracks"][0]["range_m"])
        for kind in ("lwir", "radar", "depth"):
            s = Session()
            for i in range(2):
                f = frame(i * 100, [detection()], kind=kind, lighting="zero_visible")
                self.assertEqual(s.step(encode(f), now_ms=i * 100)["state"], "PRESENT")

    def test_occlusion_reacquire_expire(self):
        a = self.step(frame(0, [detection()]))["tracks"][0]["id"]
        self.step(frame(100, [detection(0.112)]))
        r = self.step(frame(200, []))
        self.assertEqual(r["tracks"][0]["id"], a)
        self.assertEqual(r["state"], "UNKNOWN")
        self.assertEqual(r["tracks"][0]["sources"], [])
        self.assertEqual(self.step(frame(300, [detection(0.136)]))["tracks"][0]["id"], a)
        self.assertEqual(self.step(frame(901, []))["tracks"], [])
        b = self.step(frame(1000, [detection(0.14)]))["tracks"][0]["id"]
        self.assertNotEqual(a, b)

    def test_uav_fast_and_misses(self):
        out = [self.step(x["frame"]) for x in sequences()["fast_uav"]]
        self.assertEqual(len({t["id"] for r in out for t in r["tracks"]}), 1)
        self.assertEqual(out[8]["tracks"][0]["state"], "coasting")
        self.assertEqual(out[10]["tracks"][0]["state"], "observed")

    def test_camera_pan_stationary_object(self):
        for i in range(12):
            r = self.step(frame(i * 100, [detection(0.4 - 0.008 * i)], dx=-0.008 if i else 0.0))
        self.assertAlmostEqual(r["tracks"][0]["velocity_normalized_per_s"][0], 0.0, places=5)

    def test_ego_object_motion_separated(self):
        out = [self.step(x["frame"]) for x in sequences()["camera_pan"]]
        self.assertAlmostEqual(
            out[-1]["tracks"][0]["velocity_normalized_per_s"][0], 0.12, delta=0.01
        )
        f = frame(2500, [detection(0.2)])
        f["ego"]["valid"] = False
        r = self.step(f)
        self.assertIsNone(r["tracks"][0]["prediction"])
        self.assertIsNone(r["tracks"][0]["velocity_normalized_per_s"])

    def test_skew_calibration_timestamp_registration(self):
        for defect in ("skew", "calibration", "future", "registration"):
            f = frame(100, [detection()])
            f["sensors"].append(sensor(100, [detection()], "depth"))
            if defect == "skew":
                f["sensors"][0]["at_ms"] = 0
            elif defect == "calibration":
                for s in f["sensors"]:
                    s["calibration_until_ms"] = 99
            elif defect == "future":
                for s in f["sensors"]:
                    s["at_ms"] = 101
            else:
                for s in f["sensors"]:
                    s["registered"] = False
            self.assertEqual(Session().step(encode(f), now_ms=100)["state"], "UNKNOWN")

    def test_crossing_ambiguity_and_no_prediction_birth(self):
        self.step(frame(0, [detection(0.3), detection(0.5)]))
        r = self.step(frame(100, [detection(0.4)]))
        self.assertIn("association_ambiguous", r["reasons"])
        self.assertEqual(r["state"], "UNKNOWN")
        self.assertEqual(len(r["tracks"]), 2)
        self.assertEqual(Session().step(encode(frame(0, [])), now_ms=0)["tracks"], [])

    def test_expired_state_deleted_and_closed(self):
        self.step(frame(0, [detection()]))
        r = self.s.watchdog(now_ms=501)
        self.assertEqual(r["tracks"], [])
        self.assertEqual(self.s._tracks, [])
        self.assertEqual(r["state"], "UNKNOWN")
        self.assertEqual(r["recommendation"]["action"], "STOP")
        self.s.close()
        self.assertEqual(self.s._serial, 0)
        self.assertIn("invalid_input", self.step(frame(600, [detection()]))["reasons"])

    def test_no_reid_or_obstruction_schema(self):
        for name in ("person_id", "embedding", "face", "history", "target", "follow", "camera_id"):
            f = frame(0, [detection()])
            f["sensors"][0]["detections"][0][name] = "secret"
            r = self.step(f)
            self.assertEqual(r["tracks"], [])
            self.assertNotIn("secret", json.dumps(r))
        f = frame(0, [detection()])
        f["mode"] = "through_obstruction"
        self.assertEqual(self.step(f)["state"], "UNKNOWN")
        with self.assertRaises(ValueError):
            evaluate(encode(frame(0, [])))

    def test_deterministic_replay_and_live_unlinkable(self):
        data = b"\n".join(encode(x["frame"]) for x in sequences()["blackout"])
        self.assertEqual(list(replay(io.BytesIO(data))), list(replay(io.BytesIO(data))))
        f = frame(0, [detection()])
        self.assertNotEqual(
            self.step(f)["tracks"][0]["id"], Session().step(encode(f), now_ms=0)["tracks"][0]["id"]
        )
        f["evidence"] = "external_unverified"
        with self.assertRaises(ValueError):
            list(replay(io.BytesIO(encode(f))))

    def test_scene_reset_lifetime_duplicate_and_error_clear(self):
        a = self.step(frame(0, [detection()]))["tracks"][0]["id"]
        for i in range(1, 101):
            r = self.step(frame(i * 100, [detection()]))
        self.assertNotEqual(a, r["tracks"][0]["id"])
        f = frame(10100, [detection()])
        f["scene_break"] = True
        self.assertNotEqual(r["tracks"][0]["id"], self.step(f)["tracks"][0]["id"])
        self.assertEqual(self.step(f)["tracks"], [])
        self.assertEqual(self.s._tracks, [])

    def test_bad_bytes_and_numeric_bounds(self):
        for value in (True, float("nan"), float("inf"), -1, 2):
            f = frame(0, [detection()])
            f["sensors"][0]["detections"][0]["score"] = value
            with self.assertRaises(ValueError):
                parse(encode(f))
        for data in (b'{"version":3,"version":3}', b"[" * 9, b"x" * 65537):
            self.assertEqual(self.s.step(data, now_ms=0)["tracks"], [])
        f = frame(0, [detection()] * 65)
        self.assertEqual(self.step(f)["tracks"], [])

    def test_low_score_cannot_birth_and_confidence_cannot_grow(self):
        self.assertEqual(self.step(frame(0, [detection(score=0.4)]))["tracks"], [])
        self.step(frame(100, [detection()]))
        r = self.step(frame(200, [detection(score=0.4)]))
        self.assertEqual(len(r["tracks"]), 1)
        self.assertEqual(r["tracks"][0]["score"], 0.4)
        self.assertLess(self.step(frame(300, []))["tracks"][0]["score"], 0.4)

    def test_range_disagreement_and_sensor_permutation(self):
        f = frame(0, [detection()])
        f["sensors"] += [
            sensor(0, [detection(range_m=3)], "radar"),
            sensor(0, [detection(range_m=9)], "depth"),
        ]
        r = self.step(f)
        self.assertIsNone(r["tracks"][0]["range_m"])
        self.assertIn("range_disagreement", r["reasons"])
        outs = []
        for sensors in itertools.permutations(f["sensors"]):
            g = dict(f, sensors=list(sensors))
            outs.append(list(replay(io.BytesIO(encode(g)))))
        self.assertTrue(all(x == outs[0] for x in outs))

    def test_translation_estimator(self):
        r = translation([[0.01, 0.02]] * 8 + [[0.2, -0.2]] * 2, spatially_distributed=True)
        self.assertTrue(r["valid"])
        self.assertAlmostEqual(r["dx"], 0.01)
        self.assertFalse(translation([[0.01, 0.02]] * 5, spatially_distributed=True)["valid"])
        self.assertFalse(translation([[0.01, 0.02]] * 8, spatially_distributed=False)["valid"])

    def test_assignment_exhaustive_oracle_and_filter_properties(self):
        rng = random.Random(97031)
        for _ in range(2100):
            n = rng.randint(1, 4)
            m = n + rng.randint(0, 1)
            costs = [[rng.randrange(100) / 10 for _ in range(m)] for _ in range(n)]
            got = sum(costs[i][j] for i, j in assignment(costs))
            expected = min(
                sum(costs[i][j] for i, j in enumerate(p))
                for p in itertools.permutations(range(m), n)
            )
            self.assertAlmostEqual(got, expected)
            axis = Axis(rng.random(), 0.001)
            for _ in range(3):
                axis.predict(rng.random(), 0.0, 0.0001)
                axis.update(rng.random(), 0.0001)
                self.assertTrue(math.isfinite(axis.x) and axis.a > 0 and axis.c > 0)
                self.assertGreaterEqual(axis.a * axis.c - axis.b**2, -1e-12)

    def test_pixels_are_independent_of_labels_and_empty_negative(self):
        empty = b"P5\n20 20\n255\n" + bytes([180]) * 400
        self.assertEqual(detect_pgm(empty), [])
        pixels = bytearray([180]) * 400
        for y in range(8, 11):
            for x in range(8, 11):
                pixels[y * 20 + x] = 0
        ds = detect_pgm(b"P5\n20 20\n255\n" + pixels)
        self.assertEqual(ds[0]["class"], "obstacle")
        self.assertEqual(len(ds), 1)
        with self.assertRaises(ValueError):
            detect_pgm(b"P5\n999 999\n255\n")

    def test_image_camera_registration_and_flat_negative(self):
        from rescuesense.temporal.registration import estimate_translation

        rng = random.Random(3409)
        w, h = 160, 160
        pixels = bytes(rng.randrange(256) for _ in range(w * h))
        shifted = bytearray(w * h)
        for y in range(h):
            for x in range(4, w):
                shifted[y * w + x] = pixels[y * w + x - 4]
        header = b"P5\n160 160\n255\n"
        result = estimate_translation(header + pixels, header + shifted)
        self.assertTrue(result["valid"])
        self.assertAlmostEqual(result["dx"], 4 / w)
        self.assertAlmostEqual(result["dy"], 0)
        flat = header + bytes([100]) * w * h
        self.assertFalse(estimate_translation(flat, flat)["valid"])

    def test_snapshot_expiry_cannot_outlive_support(self):
        f = frame(0, [detection()])
        f["sensors"][0]["calibration_until_ms"] = 30
        r = self.step(f)
        self.assertEqual(r["expires_at_ms"], 30)
        self.assertEqual(r["tracks"][0]["expires_at_ms"], 30)
        stalled = self.s.watchdog(now_ms=31)
        self.assertEqual(stalled["state"], "UNKNOWN")
        self.assertEqual(stalled["tracks"][0]["sources"], [])

    def test_tiny_finite_geometry_does_not_crash_or_round_to_zero(self):
        from rescuesense.temporal.math import iou

        tiny = detection(0, y=0, w=1e-300, h=1e-300)
        self.assertEqual(iou(tiny["box"], tiny["box"]), 0)
        r = self.step(frame(0, [tiny]))
        self.assertGreater(r["tracks"][0]["box"][2], 0)
        r = self.step(frame(100, [tiny]))
        self.assertNotIn("invalid_input", r["reasons"])

    def test_hard_scene_rotation_and_clock_regression(self):
        first = self.step(frame(0, [detection()]))["tracks"][0]["id"].split(":")[0]
        for i in range(1, 301):
            result = self.step(frame(i * 100, [detection()]))
        self.assertNotEqual(first, result["tracks"][0]["id"].split(":")[0])
        regressed = self.s.watchdog(now_ms=29999)
        self.assertEqual(regressed["tracks"], [])
        self.assertEqual(regressed["state"], "UNKNOWN")
        self.assertEqual(self.s._tracks, [])
