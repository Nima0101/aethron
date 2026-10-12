"""A review report requires executed controls, not merely a successful runner."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from qualification.technology import review_artifacts, review_campaign, review_declarations


def outcome(*kinds):
    class Control(unittest.TestCase):
        def passed(self):
            pass

        def skipped_control(self):
            self.skipTest("synthetic skip")

        def failed(self):
            self.fail("synthetic assertion")

        def errored(self):
            raise RuntimeError("synthetic execution error")

        @unittest.expectedFailure
        def expected(self):
            self.fail("synthetic expected failure")

        @unittest.expectedFailure
        def unexpected(self):
            pass

    suite = unittest.TestSuite(Control(kind) for kind in kinds)
    return unittest.TextTestRunner(stream=io.StringIO()).run(suite)


DRIVERS = ((review_declarations, 4), (review_artifacts, 3), (review_campaign, 3))


class ReviewResultTests(unittest.TestCase):
    def reject(self, driver, results):
        output = io.StringIO()
        with (
            patch.object(driver, "run_tests", side_effect=results),
            contextlib.redirect_stdout(output),
        ):
            with self.assertRaises(RuntimeError):
                driver.main()
        self.assertEqual(output.getvalue(), "")

    def test_baseline_must_execute_without_skips_or_expected_failures(self):
        for driver, count in DRIVERS:
            for kinds in ((), ("skipped_control",), ("passed", "expected")):
                with self.subTest(driver=driver.__name__, kinds=kinds):
                    self.reject(
                        driver,
                        [outcome(*kinds)] + [outcome("failed")] * count + [outcome("passed")],
                    )

    def test_restored_baseline_must_execute_without_skips_or_expected_failures(self):
        for driver, count in DRIVERS:
            for kinds in ((), ("skipped_control",), ("passed", "expected")):
                with self.subTest(driver=driver.__name__, kinds=kinds):
                    self.reject(
                        driver,
                        [outcome("passed")] + [outcome("failed")] * count + [outcome(*kinds)],
                    )

    def test_mutations_require_assertions_without_other_outcomes(self):
        for driver, count in DRIVERS:
            for kinds in (
                ("unexpected",),
                ("failed", "skipped_control"),
                ("failed", "expected"),
                ("failed", "unexpected"),
                ("failed", "errored"),
            ):
                with self.subTest(driver=driver.__name__, kinds=kinds):
                    self.reject(
                        driver,
                        [outcome("passed"), outcome(*kinds)]
                        + [outcome("failed")] * (count - 1)
                        + [outcome("passed")],
                    )

    def test_real_controls_still_emit_negative_evidence(self):
        for driver, count in DRIVERS:
            with self.subTest(driver=driver.__name__):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    driver.main()
                report = json.loads(output.getvalue())
                self.assertGreater(report["baseline_tests"], 0)
                self.assertIs(report["restored_baseline_passed"], True)
                mutations = report.get("mutations", report.get("negative_finding_mutations"))
                self.assertEqual(len(mutations), count)
                for result in mutations.values():
                    self.assertGreater(result["failures"], 0)
                    self.assertEqual(result["errors"], 0)
                self.assertIs(report["physical_qualification_passed"], False)
