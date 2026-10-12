"""Independent limits on what a declaration report can establish."""

import unittest

from qualification import evidence
from qualification.tests.test_evidence import encoded, fixture


class DeclarationReviewTests(unittest.TestCase):
    def test_two_age_windows_do_not_establish_live_freshness(self):
        doc = fixture()
        doc["capture"]["start_ms"] = 950
        for row in doc["records"]:
            if row["kind"] != "calibration":
                row["data"]["at_ms"] = 950
        report = evidence.validate(encoded(doc), now_ms=1150)
        self.assertEqual(report["findings"], [])
        self.assertTrue(report["declaration_checks_passed"])
        self.assertIs(report["physical_qualification_passed"], False)
        self.assertEqual(report["physical_status"], "blocked_external_evidence_and_review")
        self.assertEqual(
            evidence.validate(encoded(doc), now_ms=1151)["findings"], ["capture_stale"]
        )
        doc["capture"]["start_ms"] = 949
        doc["records"][1]["data"]["at_ms"] = 949
        self.assertEqual(evidence.validate(encoded(doc), now_ms=1150)["findings"], ["record_stale"])

    def test_input_commitment_does_not_bind_the_evaluation_instant(self):
        raw = encoded(fixture())
        first = evidence.validate(raw, now_ms=1050)
        later = evidence.validate(raw, now_ms=1151)
        self.assertEqual(first["input_sha256"], later["input_sha256"])
        self.assertTrue(first["declaration_checks_passed"])
        self.assertFalse(later["declaration_checks_passed"])
        self.assertEqual(later["findings"], ["capture_stale"])
        self.assertIs(later["artifacts_verified"], False)
        self.assertIs(later["physical_qualification_passed"], False)

    def test_extreme_clock_arithmetic_retains_both_failures(self):
        maximum = 2**53 - 1000
        doc = fixture()
        doc["capture"].update(start_ms=maximum - 50, end_ms=maximum)
        for row in doc["records"]:
            if row["kind"] == "calibration":
                row["data"].update(valid_from_ms=maximum - 50, valid_until_ms=maximum)
            else:
                row["data"]["at_ms"] = maximum
        self.assertEqual(evidence.validate(encoded(doc), now_ms=maximum)["findings"], [])
        doc["records"][1]["data"].update(offset_ms=-maximum, uncertainty_ms=maximum)
        doc["records"][4]["data"].update(offset_ms=maximum, uncertainty_ms=maximum)
        report = evidence.validate(encoded(doc), now_ms=maximum)
        self.assertEqual(report["findings"], ["clock_pair_skew", "clock_reference_skew"])
        self.assertFalse(report["declaration_checks_passed"])
        self.assertIs(report["physical_qualification_passed"], False)

    def test_foreign_domain_is_not_compared_but_binding_failure_survives(self):
        doc = fixture()
        clock = doc["records"][1]
        clock.update(clock_domain="foreign_boot", rig_sha256="0" * 64)
        clock["data"].update(at_ms=0, offset_ms=1000, uncertainty_ms=1000)
        report = evidence.validate(encoded(doc), now_ms=1050)
        self.assertEqual(report["findings"], ["clock_domain_mismatch", "rig_binding_mismatch"])
        self.assertFalse(report["declaration_checks_passed"])
        self.assertIs(report["physical_qualification_passed"], False)
