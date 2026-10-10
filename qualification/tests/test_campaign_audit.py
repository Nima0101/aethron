"""SQL candidate must retain the independently asserted campaign contract."""

import itertools

from qualification.tests import test_campaign as contract
from qualification.tests.test_evidence import encoded, fixture


class CampaignAuditTests(contract.CampaignTests):
    def evaluate(self, plan, captures):
        from qualification.campaign import evaluate
        from qualification.technology.campaign_sql import evaluate_sql

        raw = plan if type(plan) is bytes else encoded(plan)
        try:
            expected = evaluate(raw, captures)
        except ValueError as error:
            with self.assertRaisesRegex(ValueError, "^" + str(error) + "$"):
                evaluate_sql(raw, captures)
            raise
        actual = evaluate_sql(raw, captures)
        self.assertEqual(actual, expected)
        return actual

    def test_all_small_permutations_retain_failed_and_reused_attempts(self):
        plan = contract.plan_fixture()
        doc = fixture()
        doc["records"][0]["data"]["valid_until_ms"] = 1049
        rows = [contract.capture(), contract.capture(), contract.capture(doc)]
        expected = self.evaluate(plan, rows)
        self.assertEqual(expected["capture_counts"]["eligible"], 0)
        self.assertIn("declaration_calibration_interval", expected["findings"])
        for order in itertools.permutations(rows):
            self.assertEqual(self.evaluate(plan, list(order)), expected)

    def test_maximum_cases_and_rows_keep_all_ordinals(self):
        plan = contract.plan_fixture()
        template = plan["cases"][0]
        plan["cases"] = [dict(template, id=f"case{i}", minimum_captures=4) for i in range(16)]
        rows = [
            dict(contract.capture(case_id=f"case{i // 4}"), manifest=encoded(fixture()) + b" " * i)
            for i in range(64)
        ]
        report = self.evaluate(plan, rows)
        self.assertTrue(report["declaration_coverage_complete"])
        self.assertEqual(report["capture_counts"], {"submitted": 64, "eligible": 64, "rejected": 0})
        self.assertEqual(
            report["cases"], [{"case_index": i, "required": 4, "eligible": 4} for i in range(16)]
        )
        self.assertEqual(self.evaluate(plan, list(reversed(rows))), report)
