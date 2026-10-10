"""Executable managed-runtime parity experiment, with synthetic wire only."""

import importlib.util
import sys
import unittest
from pathlib import Path


class LifecycleAuditTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[2] / "scripts/robotics_lifecycle_audit_v2.py"
        self.assertTrue(path.is_file(), "missing managed lifecycle comparison")
        spec = importlib.util.spec_from_file_location("lifecycle_audit", path)
        self.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)

    def test_managed_candidate_matches_state_values_and_provenance(self):
        cases = self.api.corpus()
        self.assertGreaterEqual(len(cases), 8)
        result = self.api.compare(cases)
        self.assertTrue(result["parity"])
        self.assertGreater(result["steps"], 30)

    def test_close_expiry_and_clock_latches_have_independent_expectations(self):
        results = dict(
            zip((c["name"] for c in self.api.corpus()), self.api.reference(self.api.corpus()))
        )
        self.assertEqual(results["expiry"][-1]["reason"], "receive_expired")
        self.assertEqual(results["rollback"][-1]["reason"], "local_clock_invalid")
        self.assertEqual(results["boot_reset"][-1]["reason"], "source_clock_reset")
        self.assertEqual(results["closed"][-1]["reason"], "closed")

    def test_child_rejects_ambiguous_or_nonfinite_json_before_parity(self):
        for payload in (
            '{"results": [1], "results": []}',
            '{"results": [{"perception_eligible": true, "perception_eligible": false}]}',
            '{"results": [], "peak_rss_kib": NaN}',
            '{"results": [], "peak_rss_kib": Infinity}',
            '{"results": [], "peak_rss_kib": 1e999}',
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.api._child(
                    [sys.executable, "-c", "import sys; print(sys.argv[1])", payload], []
                )

    def test_child_preserves_valid_authority_clock_and_fractional_types(self):
        payload = '{"results": [{"perception_eligible": false, "receive_ns": "9007199254740993", "values": [0.10000000149011612]}], "peak_rss_kib": 42}'
        value, elapsed = self.api._child(
            [sys.executable, "-c", "import sys; print(sys.argv[1])", payload], []
        )
        self.assertIs(value["results"][0]["perception_eligible"], False)
        self.assertEqual(value["results"][0]["receive_ns"], "9007199254740993")
        self.assertEqual(value["results"][0]["values"], [0.10000000149011612])
        self.assertIs(type(value["peak_rss_kib"]), int)
        self.assertGreater(elapsed, 0)

    def test_parity_distinguishes_boolean_authority_from_numeric_zero(self):
        self.assertTrue(callable(getattr(self.api, "check_parity", None)))
        expected = [{"perception_eligible": False, "values": [1.0]}]
        self.api.check_parity(expected, [{"perception_eligible": False, "values": [1]}])
        for value in (0, None, "false"):
            with self.assertRaisesRegex(ValueError, "managed_lifecycle_parity_failed"):
                self.api.check_parity(expected, [{"perception_eligible": value, "values": [1]}])


if __name__ == "__main__":
    unittest.main()
