import json
import unittest
from pathlib import Path

from aethron_edge.client import Observation

ROOT = Path(__file__).resolve().parents[2]


class ClientExpiry(unittest.TestCase):
    def envelope(self):
        result = json.loads((ROOT / "contracts/fixtures/v3/blackout-output.json").read_text())[
            "results"
        ][0]
        return {
            "api_version": "1",
            "kind": "scene",
            "sequence": 1,
            "session": "a" * 32,
            "clock": {"domain": "edge_monotonic", "emitted_ms": 0, "valid_for_ms": 100},
            "result": result,
        }

    def test_unbounded_transit_is_delayed_and_disconnect_erases(self):
        value = Observation()
        value.accept(self.envelope(), received_ns=0)
        self.assertEqual(value.view(now_ns=50_000_000)["label"], "delayed_observation")
        self.assertEqual(value.view(now_ns=50_000_000)["current_state"], "UNKNOWN")
        self.assertEqual(value.view(now_ns=101_000_000)["label"], "expired")
        value.accept(self.envelope(), received_ns=0)
        value.disconnect()
        self.assertEqual(value.view(now_ns=0)["label"], "expired")
        self.assertIsNone(value.scene)

    def test_unknown_enum_and_clock_suspension_fail_closed(self):
        value = Observation()
        bad = self.envelope()
        bad["result"]["state"] = "SAFE"
        with self.assertRaises(ValueError):
            value.accept(bad, received_ns=0)
        self.assertIsNone(value.scene)
        value.accept(self.envelope(), received_ns=100)
        self.assertEqual(value.view(now_ns=0)["label"], "expired")
