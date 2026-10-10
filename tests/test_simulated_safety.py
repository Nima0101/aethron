import json
import unittest
from pathlib import Path

from aethron.schema import CONTRACTS, MAX_TIME
from aethron.simulated_safety import DefensiveSimulation


def data(at=100, **changes):
    value = {
        "version": 1,
        "at_ms": at,
        "expires_at_ms": at + 100,
        "evidence": "synthetic",
        "state": "PRESENT",
        "clock_domain": "host_monotonic_ms",
    }
    value.update(changes)
    return json.dumps(value).encode()


class SimulatedSafety(unittest.TestCase):
    def test_portable_vectors_and_exported_shape(self):
        root = Path(__file__).resolve().parents[1] / "contracts"
        vectors = json.loads((root / "fixtures/simulation/defensive-v1.json").read_text())
        schema = json.loads((root / "simulation/defensive-v1.schema.json").read_text())
        for case in vectors["cases"]:
            with self.subTest(case=case["name"]):
                out = DefensiveSimulation(case["contract"]).step(
                    case["input_utf8"].encode(), now_ms=case["now_ms"]
                )
                self.assertEqual(set(out), set(schema["$defs"]["response"]["required"]))
                for key, value in case["expected"].items():
                    self.assertEqual(out[key], value)
                self.assertFalse(out["motion_authority"])

    def test_defensive_contracts_never_authorize_motion(self):
        for contract, action in CONTRACTS.items():
            out = DefensiveSimulation(contract).step(data(), now_ms=100)
            self.assertTrue(out["accepted"])
            self.assertTrue(out["simulation_only"])
            self.assertFalse(out["motion_authority"])
            self.assertTrue(out["requires_independent_controller"])
            self.assertEqual(out["action"], action)
            self.assertEqual(out["evidence"], "synthetic")
            self.assertEqual(out["state"], "PRESENT")

    def test_unknown_is_not_absence_or_permission(self):
        out = DefensiveSimulation("vehicle_stop").step(data(state="UNKNOWN"), now_ms=100)
        self.assertTrue(out["accepted"])
        self.assertEqual(out["state"], "UNKNOWN")
        self.assertEqual(out["action"], "STOP")

    def test_declared_expiry_cannot_extend_current_support_age(self):
        out = DefensiveSimulation("vehicle_stop").step(data(0, expires_at_ms=200), now_ms=50)
        self.assertTrue(out["accepted"])
        self.assertEqual(out["expires_at_ms"], 100)

    def test_unsupported_evidence_clocks_and_private_fields(self):
        for changes in (
            {"evidence": "recorded"},
            {"evidence": "external_unverified"},
            {"clock_domain": "ros_time"},
            {"person_id": "private-content"},
            {"action": "MOVE"},
            {"state": "SAFE"},
            {"version": True},
        ):
            with self.subTest(changes=changes):
                out = DefensiveSimulation("drone_hover").step(data(**changes), now_ms=100)
                self.assertFalse(out["accepted"])
                self.assertEqual(out["state"], "UNKNOWN")
                self.assertIsNone(out["evidence"])
                self.assertEqual(out["action"], "HOVER")
                self.assertEqual(out["expires_at_ms"], 100)
                self.assertNotIn("private-content", json.dumps(out))

    def test_exact_age_expiry_and_future_bounds(self):
        cases = [
            (0, 200, 100, True),
            (0, 200, 101, False),
            (100, 200, 200, False),
            (101, 201, 100, False),
            (100, 301, 100, False),
        ]
        for at, until, now, accepted in cases:
            with self.subTest(at=at, until=until, now=now):
                out = DefensiveSimulation("warn").step(data(at, expires_at_ms=until), now_ms=now)
                self.assertEqual(out["accepted"], accepted)

    def test_watermarks_survive_errors_and_watchdog(self):
        model = DefensiveSimulation("vehicle_stop")
        model.step(data(), now_ms=100)
        model.watchdog(now_ms=150)
        self.assertFalse(model.step(data(140), now_ms=140)["accepted"])
        self.assertFalse(model.step(data(100), now_ms=150)["accepted"])
        self.assertTrue(model.step(data(151), now_ms=151)["accepted"])

    def test_bad_bytes_types_and_configuration(self):
        payloads = [
            b"[" * 9,
            b"x" * 2049,
            b'{"version":1,"version":1}',
            {},
            data(at_ms=True),
            data(at_ms=float("nan")),
        ]
        model = DefensiveSimulation("vehicle_stop")
        for payload in payloads:
            self.assertFalse(model.step(payload, now_ms=100)["accepted"])
        for now in (True, -1, MAX_TIME + 1, float("nan"), "private-clock"):
            out = model.watchdog(now_ms=now)
            self.assertEqual(out["at_ms"], 100)
            self.assertFalse(out["accepted"])
        with self.assertRaises(ValueError):
            DefensiveSimulation("MOVE")

    def test_loss_close_and_mutation_do_not_retain_evidence(self):
        model = DefensiveSimulation("drone_land")
        model.step(data(evidence="recorded"), now_ms=100)
        out = model.watchdog(now_ms=101)
        self.assertEqual(out["state"], "UNKNOWN")
        self.assertIn("invalid_input", out["reasons"])
        out["reasons"].append("private-content")
        self.assertNotIn("private-content", json.dumps(model.watchdog(now_ms=102)))
        model.close()
        self.assertFalse(model.step(data(103), now_ms=103)["accepted"])
        self.assertIn("closed", model.watchdog(now_ms=104)["reasons"])


if __name__ == "__main__":
    unittest.main()
