"""Executable managed-runtime parity experiment, with synthetic wire only."""

import importlib.util
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

    def test_parity_distinguishes_boolean_authority_from_numeric_zero(self):
        self.assertTrue(callable(getattr(self.api, "check_parity", None)))
        expected = [{"perception_eligible": False, "values": [1.0]}]
        self.api.check_parity(expected, [{"perception_eligible": False, "values": [1]}])
        for value in (0, None, "false"):
            with self.assertRaisesRegex(ValueError, "managed_lifecycle_parity_failed"):
                self.api.check_parity(expected, [{"perception_eligible": value, "values": [1]}])


if __name__ == "__main__":
    unittest.main()
