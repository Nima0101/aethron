"""Comparison evidence must include executed tests and actual candidate calls."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from qualification.technology import compare_campaign, compare_ingress
from qualification.tests.test_review_results import outcome


class ComparisonResultTests(unittest.TestCase):
    def test_ingress_collection_rejects_incomplete_results(self):
        for kinds in ((), ("skipped_control",), ("passed", "expected")):
            with self.subTest(kinds=kinds):
                result = outcome(*kinds)
                with patch.object(unittest.TextTestRunner, "run", return_value=result):
                    with self.assertRaisesRegex(RuntimeError, "^semantic_oracle_tests_failed$"):
                        compare_ingress.collect()

    def test_campaign_baseline_rejects_incomplete_results(self):
        for kinds in ((), ("skipped_control",), ("passed", "expected"), ("passed",)):
            with self.subTest(kinds=kinds):
                results = [outcome(*kinds), outcome("failed")]
                output = io.StringIO()
                with (
                    patch.object(unittest.TextTestRunner, "run", side_effect=results),
                    contextlib.redirect_stdout(output),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, "^campaign_candidate_contract_failed$"
                    ):
                        compare_campaign.main()
                self.assertEqual(output.getvalue(), "")

    def test_campaign_mutation_requires_only_assertion_failures(self):
        for kinds in (
            ("unexpected",),
            ("failed", "skipped_control"),
            ("failed", "expected"),
            ("failed", "unexpected"),
            ("failed", "errored"),
        ):
            with self.subTest(kinds=kinds):
                mutant = outcome(*kinds)
                original = unittest.TextTestRunner.run
                calls = 0

                def run(runner, suite, _original=original, _mutant=mutant):
                    nonlocal calls
                    calls += 1
                    return _original(runner, suite) if calls == 1 else _mutant

                output = io.StringIO()
                with (
                    patch.object(unittest.TextTestRunner, "run", run),
                    contextlib.redirect_stdout(output),
                ):
                    with self.assertRaisesRegex(RuntimeError, "^campaign_mutation_check_failed$"):
                        compare_campaign.main()
                self.assertEqual(output.getvalue(), "")

    def test_real_collection_and_candidate_execution_remain_available(self):
        requests = compare_ingress.collect()
        self.assertGreater(len(requests), 0)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            compare_campaign.main()
        report = json.loads(output.getvalue())
        self.assertGreater(report["test_methods"], 0)
        self.assertGreater(report["candidate_calls"], 0)
        self.assertGreater(report["duplicate_mutant_failures"], 0)
        self.assertEqual(report["duplicate_mutant_errors"], 0)
        self.assertIs(report["physical_qualification_passed"], False)
