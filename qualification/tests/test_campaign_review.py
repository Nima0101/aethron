"""Independent campaign claim controls, also applied to SQL aggregation."""

import hashlib
import unittest

from qualification import campaign
from qualification.technology import campaign_sql
from qualification.tests.test_campaign import capture, plan_fixture
from qualification.tests.test_evidence import encoded


class CampaignReviewTests(unittest.TestCase):
    def evaluate(self, plan, rows):
        raw = encoded(plan)
        actual = campaign.evaluate(raw, rows)
        self.assertEqual(actual, campaign_sql.evaluate_sql(raw, rows))
        return actual

    def test_unplanned_duplicate_invalidates_planned_capture_at_different_time(self):
        rows = [capture(), dict(capture(case_id="unknown"), now_ms=1051)]
        report = self.evaluate(plan_fixture(), rows)
        self.assertEqual(report, self.evaluate(plan_fixture(), list(reversed(rows))))
        self.assertEqual(report["capture_counts"], {"submitted": 2, "eligible": 0, "rejected": 2})
        self.assertEqual(
            report["findings"],
            ["capture_coverage_missing", "capture_reused", "capture_unplanned"],
        )

    def test_commitment_retains_duplicate_triples_and_numeric_time_order(self):
        rows = [
            {"case_id": case, "manifest": b"abc", "now_ms": now}
            for case, now in (("z", 10), ("a", 11), ("a", 2), ("a", 2))
        ]
        report = self.evaluate(plan_fixture(), rows)
        # Literal wire preimage: no sorting/serialization helper from either implementation.
        digest = b"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        preimage = (
            b'aethron.qualification.captures.v1\0[["a","' + digest + b'",2],'
            b'["a","' + digest + b'",2],["a","' + digest + b'",11],'
            b'["z","' + digest + b'",10]]'
        )
        self.assertEqual(report["captures_sha256"], hashlib.sha256(preimage).hexdigest())
        self.assertEqual(report, self.evaluate(plan_fixture(), list(reversed(rows))))
        self.assertEqual(report["capture_counts"], {"submitted": 4, "eligible": 0, "rejected": 4})
        # Unknown-case bytes are committed and rejected, not semantically evaluated.
        self.assertEqual(
            report["findings"],
            ["capture_coverage_missing", "capture_reused", "capture_unplanned"],
        )

    def test_satisfied_minimum_does_not_erase_bad_or_unplanned_attempts(self):
        rows = [
            capture(),
            dict(capture(), manifest=b"abc"),
            dict(capture(case_id="unknown"), manifest=b"def"),
        ]
        report = self.evaluate(plan_fixture(), rows)
        self.assertEqual(report["cases"], [{"case_index": 0, "required": 1, "eligible": 1}])
        self.assertEqual(report["capture_counts"], {"submitted": 3, "eligible": 1, "rejected": 2})
        self.assertEqual(report["findings"], ["capture_invalid", "capture_unplanned"])
        self.assertFalse(report["declaration_coverage_complete"])

    def test_reference_hashes_bind_plan_but_do_not_verify_contents(self):
        plan = plan_fixture()
        original = self.evaluate(plan, [capture()])
        for key in ("domain_sha256", "procedure_sha256"):
            changed = self.evaluate(dict(plan, **{key: "f" * 64}), [capture()])
            self.assertNotEqual(original["plan_sha256"], changed["plan_sha256"])
            self.assertEqual(original["captures_sha256"], changed["captures_sha256"])
            self.assertTrue(changed["declaration_coverage_complete"])
            for flag in (
                "domain_verified",
                "procedure_verified",
                "artifact_authenticity_verified",
                "physical_qualification_passed",
            ):
                self.assertIs(changed[flag], False)

    def test_formatting_distinct_declarations_are_not_acquisition_independence(self):
        plan = plan_fixture()
        plan["cases"][0]["minimum_captures"] = 2
        first = capture()
        report = self.evaluate(plan, [first, dict(first, manifest=first["manifest"] + b" ")])
        self.assertEqual(report["capture_counts"], {"submitted": 2, "eligible": 2, "rejected": 0})
        self.assertTrue(report["declaration_coverage_complete"])
        self.assertIs(report["physical_qualification_passed"], False)


if __name__ == "__main__":
    unittest.main()
