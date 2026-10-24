"""Synthetic integration evidence only; no device or physical-frame qualification."""

import json
import random
import unittest
from pathlib import Path

from aethron.temporal import Session
from aethron.temporal.fixtures import detection, encode, frame, sensor
from aethron.world import CLOCK_DOMAIN, COORDINATE_FRAME, WorldModel


def step(world, f, **kwargs):
    return world.step(
        encode(f),
        now_ms=f["at_ms"],
        coordinate_frame=COORDINATE_FRAME,
        clock_domain=CLOCK_DOMAIN,
        **kwargs,
    )


def canonical(scene, ids):
    """Test-local ordinals only; never add canonical identity to the live API."""
    result = json.loads(json.dumps(scene))
    for track in result["tracks"]:
        track["id"] = ids.setdefault(track["id"], len(ids) + 1)
    return result


class WorldSimulation(unittest.TestCase):
    def test_frozen_sequences_equal_direct_session_baseline(self):
        paths = sorted((Path(__file__).resolve().parents[1] / "data/temporal").glob("*.json"))
        self.assertGreaterEqual(len(paths), 8)
        for path in paths:
            with self.subTest(sequence=path.stem):
                world, baseline = WorldModel(), Session()
                world_ids, baseline_ids = {}, {}
                for entry in json.loads(path.read_text()):
                    f = entry["frame"]
                    actual = step(world, f)
                    expected = baseline.step(encode(f), now_ms=f["at_ms"])
                    self.assertFalse(actual["quarantined"])
                    self.assertEqual(actual["world_model_version"], 1)
                    self.assertEqual(actual["coordinate_frame"], COORDINATE_FRAME)
                    self.assertEqual(actual["clock_domain"], CLOCK_DOMAIN)
                    self.assertEqual(
                        canonical(actual["scene"], world_ids), canonical(expected, baseline_ids)
                    )
                world.close()
                baseline.close()

    def test_blackout_fusion_all_loss_and_reentry(self):
        world = WorldModel()
        f = frame(0, [detection()], kind="rgb")
        f["sensors"].append(sensor(0, [detection()], "lwir"))
        first = step(world, f)["scene"]["tracks"][0]
        f = frame(100, [detection()], kind="rgb", lighting="zero_visible")
        f["sensors"].append(sensor(100, [detection()], "lwir"))
        f["sensors"].append(sensor(100, [detection(range_m=8)], "depth"))
        current = step(world, f)["scene"]["tracks"][0]
        self.assertEqual(current["id"], first["id"])
        self.assertEqual(current["sources"], ["depth", "lwir"])
        self.assertEqual(current["range_m"], 8)
        loss = step(world, frame(200, []))["scene"]
        self.assertEqual(loss["state"], "UNKNOWN")
        self.assertEqual(loss["tracks"][0]["sources"], [])
        self.assertIsNone(loss["tracks"][0]["range_m"])
        self.assertFalse(loss["tracks"][0]["prediction"]["evidence"])
        self.assertLessEqual(loss["tracks"][0]["score"], current["score"])
        self.assertEqual(step(world, frame(601, []))["scene"]["tracks"], [])
        new = step(world, frame(700, [detection()]))["scene"]["tracks"][0]
        self.assertNotEqual(new["id"], first["id"])

    def test_unregistered_skewed_expired_future_support_is_not_evidence(self):
        for defect in ("registration", "calibration", "skew", "future", "stale"):
            with self.subTest(defect=defect):
                world = WorldModel()
                f = frame(200, [detection()])
                s = f["sensors"][0]
                if defect == "registration":
                    s["registered"] = False
                elif defect == "calibration":
                    s["calibration_until_ms"] = 199
                elif defect == "skew":
                    s["at_ms"] = 149
                    f["sensors"].append(sensor(200, [detection()], "radar"))
                elif defect == "future":
                    s["at_ms"] = 201
                else:
                    s["at_ms"] = 99
                out = step(world, f)["scene"]
                self.assertEqual(out["state"], "UNKNOWN")
                self.assertEqual(out["tracks"], [])
                self.assertTrue(out["reasons"])

    def test_range_disagreement_retained_through_watchdog(self):
        world = WorldModel()
        f = frame(0, [detection(range_m=8)], kind="depth")
        f["sensors"].append(sensor(0, [detection(range_m=20)], "radar"))
        out = step(world, f)["scene"]
        self.assertEqual(out["tracks"][0]["sources"], ["depth", "radar"])
        self.assertIsNone(out["tracks"][0]["range_m"])
        self.assertIn("range_disagreement", out["reasons"])
        self.assertIn("range_disagreement", world.watchdog(now_ms=1)["scene"]["reasons"])

    def test_capacity_and_track_rotation_remain_bounded(self):
        world = WorldModel()
        ds = [detection(x=0.02 + (i % 8) * 0.1, y=0.02 + (i // 8) * 0.1) for i in range(64)]
        out = step(world, frame(0, ds))["scene"]
        self.assertEqual(len(out["tracks"]), 32)
        self.assertIn("capacity", out["reasons"])
        world = WorldModel()
        first = step(world, frame(0, [detection()]))["scene"]["tracks"][0]["id"]
        for at in range(100, 10100, 100):
            out = step(world, frame(at, [detection()]))["scene"]
        self.assertNotEqual(first, out["tracks"][0]["id"])

    def test_scene_and_evidence_changes_break_linkage(self):
        world = WorldModel()
        prior = step(world, frame(0, [detection()]))["scene"]["tracks"][0]["id"]
        for at, evidence in enumerate(("recorded", "external_unverified", "synthetic"), 1):
            f = frame(at * 100, [detection()])
            f["evidence"] = evidence
            out = step(world, f)["scene"]
            self.assertEqual(out["evidence"], evidence)
            self.assertNotEqual(prior, out["tracks"][0]["id"])
            prior = out["tracks"][0]["id"]
        f = frame(400, [detection()])
        f["scene_break"] = True
        self.assertNotEqual(prior, step(world, f)["scene"]["tracks"][0]["id"])

    def test_seeded_malformed_bytes_never_echo_or_leave_tracks(self):
        rng = random.Random(6)
        payloads = [b"x" * 65537, b"[" * 9, b'{"version":3,"version":3}', b"private-marker"]
        payloads += [
            bytes(rng.randrange(256) for _ in range(rng.randrange(1, 96))) for _ in range(64)
        ]
        for payload in payloads:
            with self.subTest(size=len(payload)):
                world = WorldModel()
                step(world, frame(0, [detection()]))
                out = world.step(
                    payload, now_ms=1, coordinate_frame=COORDINATE_FRAME, clock_domain=CLOCK_DOMAIN
                )
                self.assertTrue(out["quarantined"])
                self.assertEqual(out["scene"]["tracks"], [])
                self.assertEqual(out["scene"]["state"], "UNKNOWN")
                self.assertNotIn("private-marker", json.dumps(out))
                self.assertEqual(world.watchdog(now_ms=2)["scene"]["tracks"], [])


if __name__ == "__main__":
    unittest.main()
