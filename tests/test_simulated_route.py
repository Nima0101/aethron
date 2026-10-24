import json
import unittest

from aethron.simulated_plan import SimulationPlan
from aethron.simulated_route import SimulationRoute


def request(at=0, **changes):
    obj = {
        "version": 1,
        "at_ms": at,
        "expires_at_ms": at + 100,
        "evidence": "synthetic",
        "coordinate_frame": "synthetic_grid",
        "clock_domain": "host_monotonic_ms",
        "grid": [["free"] * 2 for _ in range(2)],
        "start": [0, 0],
        "goal": [1, 1],
    }
    obj.update(changes)
    return json.dumps(obj).encode()


class SimulatedRoute(unittest.TestCase):
    def test_resource_probe_exercises_route_search(self):
        from scripts.simulated_plan_probe import run

        report = run(route=True)
        self.assertEqual(report["mode"], "route")
        self.assertEqual(report["path_cells"], 31)
        self.assertEqual(len(report["wall_samples_ms"]), 100)

    def test_deterministic_shortest_route_and_independent_checker(self):
        raw = request()
        out = SimulationRoute("vehicle_stop").step(raw, now_ms=0)
        self.assertTrue(out["route_found"])
        self.assertEqual(out["path"], [[0, 0], [1, 0], [1, 1]])
        obj = json.loads(raw)
        del obj["start"]
        del obj["goal"]
        obj["path"] = out["path"]
        self.assertTrue(
            SimulationPlan("vehicle_stop").step(json.dumps(obj).encode(), now_ms=0)[
                "plan_admissible"
            ]
        )
        self.assertFalse(out["recommendation"]["motion_authority"])
        self.assertEqual(out["recommendation"]["action"], "STOP")

    def test_unknown_blocked_and_disconnected_endpoints(self):
        for grid, reason in (
            ([["unknown", "free"], ["free", "free"]], "endpoint_not_free"),
            ([["free", "free"], ["free", "blocked"]], "endpoint_not_free"),
            ([["free", "unknown"], ["blocked", "free"]], "unreachable"),
        ):
            out = SimulationRoute("warn").step(request(grid=grid), now_ms=0)
            self.assertFalse(out["route_found"])
            self.assertEqual(out["path"], [])
            self.assertIn(reason, out["reasons"])
        self.assertEqual(
            SimulationRoute("warn").step(request(goal=[0, 0]), now_ms=0)["path"], [[0, 0]]
        )

    def test_detour_succeeds_where_straight_line_baseline_fails(self):
        raw = request(
            grid=[["free", "blocked", "free"], ["free", "blocked", "free"], ["free"] * 3],
            goal=[2, 0],
        )
        out = SimulationRoute("warn").step(raw, now_ms=0)
        self.assertTrue(out["route_found"])
        self.assertEqual(len(out["path"]), 7)
        obj = json.loads(raw)
        del obj["start"]
        del obj["goal"]
        obj["path"] = [[0, 0], [1, 0], [2, 0]]
        self.assertFalse(
            SimulationPlan("warn").step(json.dumps(obj).encode(), now_ms=0)["plan_admissible"]
        )

    def test_no_truncation_of_route_over_64_cells(self):
        grid = [["blocked"] * 16 for _ in range(15)]
        for y in range(0, 15, 2):
            grid[y] = ["free"] * 16
            if y < 14:
                grid[y + 1][15 if (y // 2) % 2 == 0 else 0] = "free"
        out = SimulationRoute("warn").step(request(grid=grid, goal=[0, 14]), now_ms=0)
        self.assertFalse(out["route_found"])
        self.assertEqual(out["path"], [])
        self.assertIn("path_limit", out["reasons"])

    def test_strict_request_bounds_and_no_private_echo(self):
        for change in (
            {"start": [True, 0]},
            {"goal": [1.0, 1]},
            {"goal": [-1, 0]},
            {"goal": [16, 0]},
            {"grid": [["free"] * 17]},
            {"grid": [[]]},
            {"path": []},
            {"person_id": "private"},
            {"evidence": "recorded"},
            {"clock_domain": "utc"},
            {"coordinate_frame": "map"},
        ):
            out = SimulationRoute("warn").step(request(**change), now_ms=0)
            self.assertFalse(out["route_found"])
            self.assertEqual(out["path"], [])
            self.assertNotIn("private", json.dumps(out))
        for raw in (b"[" * 9, b"x" * 8193, b"\xff", {}, b'{"start":[],"start":[]}'):
            self.assertFalse(SimulationRoute("warn").step(raw, now_ms=0)["route_found"])

    def test_expiry_future_and_invalid_clocks_do_not_export_route(self):
        for now in (100, 101, -1, True, float("nan")):
            self.assertFalse(
                SimulationRoute("warn").step(request(expires_at_ms=200), now_ms=now)["route_found"]
            )
        self.assertFalse(SimulationRoute("warn").step(request(1), now_ms=0)["route_found"])
        out = SimulationRoute("warn").step(request(expires_at_ms=200), now_ms=90)
        self.assertTrue(out["route_found"])
        self.assertEqual(out["recommendation"]["expires_at_ms"], 100)

    def test_failure_watermarks_diagnostics_and_recovery(self):
        model = SimulationRoute("warn")
        model.step(request(grid=[["free", "unknown"], ["blocked", "free"]]), now_ms=0)
        self.assertIn("unreachable", model.watchdog(now_ms=1)["reasons"])
        out = model.step(request(), now_ms=1)
        self.assertFalse(out["route_found"])
        self.assertIn("frame_regression", out["reasons"])
        self.assertIn("unreachable", out["reasons"])
        self.assertFalse(model.step(request(), now_ms=0)["route_found"])
        self.assertTrue(model.step(request(2), now_ms=2)["route_found"])

    def test_detached_results_and_terminal_close(self):
        model = SimulationRoute("warn")
        out = model.step(request(), now_ms=0)
        out["path"][0][0] = 99
        out["reasons"].append("private")
        self.assertNotIn("private", json.dumps(model.watchdog(now_ms=1)))
        self.assertEqual(model.watchdog(now_ms=1)["path"], [])
        model.close()
        self.assertFalse(model.step(request(2), now_ms=2)["route_found"])
        self.assertEqual(model.watchdog(now_ms=3)["path"], [])

    def test_all_tiny_maps_match_floyd_warshall_distances(self):
        cells = [(0, 0), (1, 0), (0, 1), (1, 1)]
        for mask in range(16):
            free = {c for i, c in enumerate(cells) if mask & (1 << i)}
            grid = [["free" if (x, y) in free else "unknown" for x in range(2)] for y in range(2)]
            dist = {
                (a, b): 0
                if a == b and a in free
                else 1
                if a in free and b in free and ((a[0] == b[0]) != (a[1] == b[1]))
                else 99
                for a in cells
                for b in cells
            }
            for k in cells:
                for a in cells:
                    for b in cells:
                        dist[a, b] = min(dist[a, b], dist[a, k] + dist[k, b])
            for a in cells:
                for b in cells:
                    raw = request(grid=grid, start=a, goal=b)
                    out = SimulationRoute("warn").step(raw, now_ms=0)
                    self.assertEqual(out["route_found"], dist[a, b] < 99, (mask, a, b))
                    if out["route_found"]:
                        self.assertEqual(len(out["path"]), dist[a, b] + 1)
                        obj = json.loads(raw)
                        del obj["start"]
                        del obj["goal"]
                        obj["path"] = out["path"]
                        self.assertTrue(
                            SimulationPlan("warn").step(json.dumps(obj).encode(), now_ms=0)[
                                "plan_admissible"
                            ]
                        )


if __name__ == "__main__":
    unittest.main()
