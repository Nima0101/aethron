"""Coverage and reference matching are independent, non-qualifying gates."""

import hashlib
import importlib.util
import json
import unittest

from qualification.tests.test_campaign import capture
from qualification.tests.test_campaign_references import reference_plan
from qualification.tests.test_evidence import encoded


class CampaignBundleTests(unittest.TestCase):
    def evaluate(self, plan, captures, domain=b"abc", procedure=b"def"):
        self.assertIsNotNone(importlib.util.find_spec("qualification.campaign_bundle"))
        from qualification.campaign_bundle import evaluate

        return evaluate(plan, captures, domain, procedure)

    def test_both_checks_are_required_without_granting_qualification(self):
        for covered in (False, True):
            for matched in (False, True):
                with self.subTest(covered=covered, matched=matched):
                    report = self.evaluate(
                        reference_plan(),
                        [capture()] if covered else [],
                        b"abc" if matched else b"changed",
                    )
                    self.assertIs(report["software_checks_passed"], covered and matched)
                    self.assertIs(report["coverage"]["declaration_coverage_complete"], covered)
                    self.assertIs(report["references"]["reference_bytes_verified"], matched)
                    for key in (
                        "artifact_bytes_verified",
                        "artifact_authenticity_verified",
                        "domain_verified",
                        "procedure_verified",
                        "physical_qualification_passed",
                    ):
                        self.assertIs(report[key], False)

    def test_combined_negative_evidence_is_retained(self):
        report = self.evaluate(reference_plan(), [capture(), capture()], b"bad", b"bad")
        self.assertEqual(
            report["coverage"]["findings"], ["capture_coverage_missing", "capture_reused"]
        )
        self.assertEqual(
            report["references"]["reference_findings"],
            ["domain_digest_mismatch", "procedure_digest_mismatch"],
        )
        self.assertEqual(
            report["coverage"]["capture_counts"], {"submitted": 2, "eligible": 0, "rejected": 2}
        )
        self.assertIs(report["software_checks_passed"], False)

    def test_exact_plan_bytes_bind_both_nested_reports(self):
        plan = reference_plan()
        first = self.evaluate(plan, [capture()])
        for raw in (plan, plan + b" "):
            report = self.evaluate(raw, [capture()])
            digest = hashlib.sha256(raw).hexdigest()
            self.assertEqual(report["plan_sha256"], digest)
            self.assertEqual(report["coverage"]["plan_sha256"], digest)
            self.assertEqual(report["references"]["plan_sha256"], digest)
            self.assertTrue(report["software_checks_passed"])
        self.assertNotEqual(first["plan_sha256"], report["plan_sha256"])

    def test_capture_commitment_preserves_instants_and_duplicates(self):
        row = capture()
        later = dict(row, now_ms=1051)
        first = self.evaluate(reference_plan(), [row])
        second = self.evaluate(reference_plan(), [later])
        self.assertNotEqual(
            first["coverage"]["captures_sha256"], second["coverage"]["captures_sha256"]
        )
        duplicate = self.evaluate(reference_plan(), [row, later])
        self.assertEqual(duplicate, self.evaluate(reference_plan(), [later, row]))
        self.assertFalse(duplicate["software_checks_passed"])

    def test_invalid_input_and_forged_reports_raise_fixed_error(self):
        plan = reference_plan()
        for args in (
            (b'{"PRIVATE":', [], b"abc", b"def"),
            (plan, {"declaration_coverage_complete": True}, b"abc", b"def"),
            (plan, [capture()] * 65, b"abc", b"def"),
            (plan, [], bytearray(b"abc"), b"def"),
            (plan, [], b"abc", b"x" * 1048577),
        ):
            with self.subTest(types=[type(x).__name__ for x in args]):
                with self.assertRaisesRegex(ValueError, "^invalid_campaign_bundle$"):
                    self.evaluate(*args)

    def test_report_does_not_echo_opaque_reference_contents(self):
        domain, procedure = b"PRIVATE_DOMAIN", b"PRIVATE_PROCEDURE"
        report = self.evaluate(reference_plan(domain, procedure), [capture()], domain, procedure)
        self.assertTrue(report["software_checks_passed"])
        self.assertNotIn("PRIVATE", json.dumps(report))

    def test_composed_input_limits_remain_usable(self):
        domain, procedure = b"x" * 1048576, b"y" * 1048576
        plan = json.loads(reference_plan(domain, procedure))
        plan["cases"][0]["minimum_captures"] = 64
        row = capture()
        raw = row["manifest"]
        # Distinct declaration bytes, not evidence of independent acquisitions.
        rows = [dict(row, manifest=raw + b" " * (65536 - len(raw) - i)) for i in range(64)]
        report = self.evaluate(encoded(plan), rows, domain, procedure)
        self.assertTrue(report["software_checks_passed"])
        self.assertEqual(
            report["coverage"]["capture_counts"], {"submitted": 64, "eligible": 64, "rejected": 0}
        )
        self.assertEqual(report["references"]["reference_counts"]["supplied_bytes"], 2097152)
        self.assertIs(report["physical_qualification_passed"], False)


if __name__ == "__main__":
    unittest.main()
