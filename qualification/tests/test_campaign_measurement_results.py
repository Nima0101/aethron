"""Campaign timing evidence needs independent expected values and exact types."""

import contextlib
import io
import json
import tracemalloc
import unittest
from unittest.mock import patch

from qualification.technology import campaign_sql, compare_campaign


class CampaignMeasurementResultTests(unittest.TestCase):
    def test_contract_types_cannot_hide_behind_a_valid_maximum_workload(self):
        original = campaign_sql.evaluate_sql
        for path, convert in (
            (("version",), bool),
            (("capture_counts", "rejected"), float),
        ):
            with self.subTest(path=path):
                changed_calls = []

                def changed(
                    plan, captures, path=path, convert=convert, changed_calls=changed_calls
                ):
                    report = original(plan, captures)
                    # Leave both maximum-case tests and measurements correct.
                    # Only ordinary contract cases receive an equal wrong type.
                    if len(captures) != 64:
                        parent = report
                        for key in path[:-1]:
                            parent = parent[key]
                        parent[path[-1]] = convert(parent[path[-1]])
                        changed_calls.append(len(captures))
                    return report

                output = io.StringIO()
                with (
                    patch.object(campaign_sql, "evaluate_sql", changed),
                    contextlib.redirect_stdout(output),
                ):
                    with self.assertRaisesRegex(
                        RuntimeError, "^campaign_candidate_contract_failed$"
                    ):
                        compare_campaign.main()
                self.assertTrue(changed_calls)
                self.assertEqual(output.getvalue(), "")

    def reject_changed_result(self, engines, path, value, *, traced, at_call=None):
        original_python = compare_campaign.evaluate
        original_sql = campaign_sql.evaluate_sql
        original_plan = compare_campaign.plan_fixture
        measuring = False
        calls = {"python": 0, "sqlite": 0}

        def start_workload():
            nonlocal measuring
            measuring = True
            return original_plan()

        def changed(function, engine, *args, **kwargs):
            report = function(*args, **kwargs)
            if measuring and engine in engines and tracemalloc.is_tracing() is traced:
                calls[engine] += 1
                if at_call is None or calls[engine] == at_call:
                    parent = report
                    for key in path[:-1]:
                        parent = parent[key]
                    parent[path[-1]] = value
            return report

        def python(*args, **kwargs):
            return changed(original_python, "python", *args, **kwargs)

        def sql(*args, **kwargs):
            return changed(original_sql, "sqlite", *args, **kwargs)

        output = io.StringIO()
        with (
            patch.object(compare_campaign, "plan_fixture", start_workload),
            patch.object(compare_campaign, "evaluate", python),
            patch.object(campaign_sql, "evaluate_sql", sql),
            contextlib.redirect_stdout(output),
        ):
            with self.assertRaisesRegex(RuntimeError, "^campaign_maximum_parity_failed$"):
                compare_campaign.main()
        self.assertEqual(output.getvalue(), "")
        self.assertFalse(tracemalloc.is_tracing())

    def test_shared_wrong_results_cannot_define_the_expected_report(self):
        for path, value in (
            (("physical_qualification_passed",), True),
            (("plan_sha256",), "0" * 64),
            (("captures_sha256",), "0" * 64),
            (("capture_counts", "eligible"), 0),
            (("findings",), ["capture_coverage_missing"]),
        ):
            with self.subTest(path=path):
                self.reject_changed_result({"python", "sqlite"}, path, value, traced=False)

    def test_timed_report_types_cannot_hide_behind_numeric_equality(self):
        for engine in ("python", "sqlite"):
            for path, value in (
                (("version",), True),
                (("capture_counts", "eligible"), 64.0),
                (("cases", 0, "case_index"), False),
                (("physical_qualification_passed",), 0),
            ):
                with self.subTest(engine=engine, path=path):
                    self.reject_changed_result({engine}, path, value, traced=False)

    def test_both_traced_results_must_match_before_report_delivery(self):
        for engine in ("python", "sqlite"):
            for path, value in (
                (("capture_counts", "eligible"), 0),
                (("physical_qualification_passed",), True),
            ):
                with self.subTest(engine=engine, path=path):
                    self.reject_changed_result({engine}, path, value, traced=True)

    def test_intermittent_timed_failure_is_not_replaced_by_later_success(self):
        for engine in ("python", "sqlite"):
            with self.subTest(engine=engine):
                self.reject_changed_result(
                    {engine}, ("capture_counts", "eligible"), 0, traced=False, at_call=5
                )

    def test_real_maximum_workload_still_reports_nonqualifying_coverage(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            compare_campaign.main()
        report = json.loads(output.getvalue())
        workload = report["maximum_workload_report"]
        self.assertEqual(
            workload["capture_counts"], {"submitted": 64, "eligible": 64, "rejected": 0}
        )
        self.assertEqual(
            workload["cases"], [{"case_index": i, "required": 4, "eligible": 4} for i in range(16)]
        )
        self.assertIs(workload["physical_qualification_passed"], False)
        self.assertEqual(set(report["elapsed_ns"]), {"python", "sqlite"})
        self.assertTrue(all(len(samples) == 10 for samples in report["elapsed_ns"].values()))
        self.assertFalse(tracemalloc.is_tracing())
