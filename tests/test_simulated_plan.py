import itertools
import json
import unittest

from aethron.schema import CONTRACTS, MAX_TIME
from aethron.simulated_plan import SimulationPlan


def proposal(at=0, **changes):
    obj = {
        "version": 1,
        "at_ms": at,
        "expires_at_ms": at + 100,
        "evidence": "synthetic",
        "coordinate_frame": "synthetic_grid",
        "clock_domain": "host_monotonic_ms",
        "grid": [["free", "free"], ["unknown", "blocked"]],
        "path": [[0, 0], [1, 0]],
    }
    obj.update(changes)
    return json.dumps(obj).encode()


class SimulatedPlan(unittest.TestCase):
    def test_valid_path_never_grants_motion_authority(self):
        for contract, action in CONTRACTS.items():
            out = SimulationPlan(contract).step(proposal(), now_ms=0)
            self.assertEqual(
                set(out),
                {
                    "simulation_plan_version",
                    "input_accepted",
                    "plan_admissible",
                    "reasons",
                    "recommendation",
                },
            )
            self.assertTrue(out["input_accepted"])
            self.assertTrue(out["plan_admissible"])
            self.assertEqual(out["reasons"], [])
            self.assertEqual(out["recommendation"]["action"], action)
            self.assertEqual(out["recommendation"]["state"], "UNKNOWN")
            self.assertFalse(out["recommendation"]["motion_authority"])
            self.assertTrue(out["recommendation"]["simulation_only"])
            self.assertNotIn('"path"', json.dumps(out))
            self.assertNotIn('"grid"', json.dumps(out))

    def test_unknown_blocked_diagonal_and_jump_reject(self):
        for path, reason in (
            ([[0, 0], [0, 1]], "unknown_cell"),
            ([[1, 0], [1, 1]], "blocked_cell"),
            ([[0, 0], [1, 1]], "nonadjacent_step"),
        ):
            out = SimulationPlan("warn").step(proposal(path=path), now_ms=0)
            self.assertTrue(out["input_accepted"])
            self.assertFalse(out["plan_admissible"])
            self.assertIn(reason, out["reasons"])
        out = SimulationPlan("warn").step(
            proposal(grid=[["free"] * 3], path=[[0, 0], [2, 0]]), now_ms=0
        )
        self.assertIn("nonadjacent_step", out["reasons"])

    def test_waiting_and_maximum_shape_are_bounded(self):
        out = SimulationPlan("warn").step(
            proposal(grid=[["free"] * 16 for _ in range(16)], path=[[15, 15]] * 64), now_ms=0
        )
        self.assertTrue(out["plan_admissible"])

    def test_closed_structure_and_privacy_rejections(self):
        for changes in (
            {"grid": []},
            {"grid": [[]]},
            {"grid": [["free"], ["free", "free"]]},
            {"grid": [["free"] * 17]},
            {"grid": [["free"]] * 17},
            {"grid": [["safe"]]},
            {"path": []},
            {"path": [[0, 0]] * 65},
            {"path": [[-1, 0]]},
            {"path": [[2, 0]]},
            {"path": [[0, 2]]},
            {"path": [[True, 0]]},
            {"path": [[0.0, 0]]},
            {"path": [[0, 0, 0]]},
            {"person_id": "private"},
            {"action": "MOVE"},
            {"evidence": "recorded"},
            {"evidence": "external_unverified"},
            {"coordinate_frame": "registered_image_normalized"},
            {"clock_domain": "utc"},
            {"version": True},
            {"expires_at_ms": 100.0},
            {"at_ms": float("nan")},
        ):
            with self.subTest(changes=changes):
                out = SimulationPlan("warn").step(proposal(**changes), now_ms=0)
                self.assertFalse(out["input_accepted"])
                self.assertFalse(out["plan_admissible"])
                self.assertNotIn("private", json.dumps(out))
                self.assertEqual(out["recommendation"]["expires_at_ms"], 0)

    def test_malformed_bytes_and_duplicates_fail_closed(self):
        for raw in (b"[" * 9, b"x" * 8193, b"\xff", {}, b'{"version":1,"version":1}'):
            out = SimulationPlan("warn").step(raw, now_ms=0)
            self.assertFalse(out["plan_admissible"])
            self.assertIn("invalid_input", out["reasons"])

    def test_expiry_is_original_time_and_exclusive(self):
        for now, accepted in ((0, True), (99, True), (100, False), (101, False)):
            out = SimulationPlan("warn").step(proposal(), now_ms=now)
            self.assertEqual(out["plan_admissible"], accepted)
        out = SimulationPlan("warn").step(proposal(expires_at_ms=200), now_ms=90)
        self.assertEqual(out["recommendation"]["expires_at_ms"], 100)
        out = SimulationPlan("warn").step(proposal(expires_at_ms=200), now_ms=100)
        self.assertFalse(out["plan_admissible"])

    def test_watermarks_include_infeasible_proposals(self):
        model = SimulationPlan("warn")
        model.step(proposal(100, path=[[1, 1]]), now_ms=100)
        out = model.step(proposal(100), now_ms=100)
        self.assertFalse(out["input_accepted"])
        self.assertIn("frame_regression", out["reasons"])
        model.watchdog(now_ms=200)
        self.assertFalse(model.step(proposal(150), now_ms=150)["input_accepted"])
        self.assertTrue(model.step(proposal(201), now_ms=201)["plan_admissible"])

    def test_invalid_clocks_and_future_frames_never_admit(self):
        for now in (True, -1, MAX_TIME + 1, "secret", float("nan")):
            out = SimulationPlan("warn").step(proposal(), now_ms=now)
            self.assertFalse(out["plan_admissible"])
            self.assertNotIn("secret", json.dumps(out))
        self.assertFalse(SimulationPlan("warn").step(proposal(1), now_ms=0)["plan_admissible"])

    def test_loss_close_and_detached_results(self):
        model = SimulationPlan("warn")
        out = model.step(proposal(), now_ms=0)
        out["reasons"].append("private")
        out["recommendation"]["reasons"].append("private")
        lost = model.watchdog(now_ms=1)
        self.assertFalse(lost["plan_admissible"])
        self.assertNotIn("private", json.dumps(lost))
        self.assertEqual(lost["recommendation"]["expires_at_ms"], 1)
        model.close()
        self.assertFalse(model.step(proposal(2), now_ms=2)["plan_admissible"])
        with self.assertRaises(ValueError):
            SimulationPlan("MOVE")

    def test_known_path_failures_survive_loss_until_fresh_admission(self):
        model = SimulationPlan("warn")
        model.step(proposal(path=[[1, 1]]), now_ms=0)
        self.assertIn("blocked_cell", model.watchdog(now_ms=1)["reasons"])
        self.assertIn("blocked_cell", model.step(b"bad", now_ms=2)["reasons"])
        out = model.step(proposal(3), now_ms=3)
        self.assertTrue(out["plan_admissible"])
        self.assertEqual(out["reasons"], [])

    def test_exhaustive_tiny_grid_matches_independent_edge_oracle(self):
        cells = ((0, 0), (1, 0), (0, 1), (1, 1))
        edges = {(a, b) for a in cells for b in cells if a == b or (a[0] == b[0]) != (a[1] == b[1])}
        for mask in range(16):
            free = {c for i, c in enumerate(cells) if mask & (1 << i)}
            grid = [["free" if (x, y) in free else "unknown" for x in range(2)] for y in range(2)]
            for path in itertools.product(cells, repeat=2):
                expected = set(path) <= free and path in edges
                out = SimulationPlan("warn").step(proposal(grid=grid, path=path), now_ms=0)
                self.assertEqual(out["plan_admissible"], expected, (mask, path))


if __name__ == "__main__":
    unittest.main()
