"""Opaque campaign reference bytes cannot establish domain qualification."""

import hashlib
import importlib.util
import json
import unittest

from qualification.tests.test_campaign import plan_fixture
from qualification.tests.test_evidence import encoded


def reference_plan(domain=b"abc", procedure=b"def"):
    plan = plan_fixture()
    plan.update(
        domain_sha256=hashlib.sha256(domain).hexdigest(),
        procedure_sha256=hashlib.sha256(procedure).hexdigest(),
    )
    return encoded(plan)


class CampaignReferenceTests(unittest.TestCase):
    def bind(self, plan, domain, procedure):
        self.assertIsNotNone(importlib.util.find_spec("qualification.campaign_references"))
        from qualification.campaign_references import bind

        return bind(plan, domain, procedure)

    def test_matching_references_never_verify_domains_or_procedures(self):
        plan = reference_plan()
        report = self.bind(plan, b"abc", b"def")
        self.assertEqual(
            report,
            {
                "version": 1,
                "plan_sha256": hashlib.sha256(plan).hexdigest(),
                "reference_counts": {"supplied": 2, "matched": 2, "supplied_bytes": 6},
                "reference_findings": [],
                "reference_bytes_verified": True,
                "domain_verified": False,
                "procedure_verified": False,
                "artifact_authenticity_verified": False,
                "physical_qualification_passed": False,
            },
        )

    def test_swapped_or_changed_payloads_preserve_every_mismatch(self):
        for domain, procedure, findings, count in (
            (b"def", b"abc", ["domain_digest_mismatch", "procedure_digest_mismatch"], 0),
            (b"changed", b"def", ["domain_digest_mismatch"], 1),
            (b"abc", b"changed", ["procedure_digest_mismatch"], 1),
        ):
            with self.subTest(findings=findings):
                report = self.bind(reference_plan(), domain, procedure)
                self.assertEqual(report["reference_findings"], findings)
                self.assertEqual(report["reference_counts"]["matched"], count)
                self.assertIs(report["reference_bytes_verified"], False)

    def test_mutable_or_oversized_payloads_are_rejected(self):
        for bad in (None, "abc", bytearray(b"abc"), memoryview(b"abc"), b"x" * 1048577):
            for domain, procedure in ((bad, b"def"), (b"abc", bad)):
                with self.subTest(type=type(bad).__name__):
                    with self.assertRaisesRegex(ValueError, "^invalid_campaign_references$"):
                        self.bind(reference_plan(), domain, procedure)

    def test_exact_limits_and_empty_references_do_not_prove_content_validity(self):
        for domain, procedure in ((b"", b""), (b"x" * 1048576, b"y" * 1048576)):
            report = self.bind(reference_plan(domain, procedure), domain, procedure)
            self.assertTrue(report["reference_bytes_verified"])
            self.assertEqual(
                report["reference_counts"]["supplied_bytes"], len(domain) + len(procedure)
            )
            self.assertIs(report["domain_verified"], False)
            self.assertIs(report["physical_qualification_passed"], False)

    def test_plan_admission_is_strict_and_errors_do_not_echo_input(self):
        for raw in (
            b'{"PRIVATE":',
            reference_plan().replace(b'"version":1', b'"version":1,"version":1'),
            reference_plan() + b" " * 65536,
            encoded(dict(plan_fixture(), domain_verified=True)),
        ):
            with self.assertRaisesRegex(ValueError, "^invalid_campaign_references$"):
                self.bind(raw, b"abc", b"def")

    def test_report_omits_reference_contents(self):
        domain, procedure = b"PRIVATE_DOMAIN", b"PRIVATE_PROCEDURE"
        report = self.bind(reference_plan(domain, procedure), domain, procedure)
        self.assertTrue(report["reference_bytes_verified"])
        self.assertNotIn("PRIVATE", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
