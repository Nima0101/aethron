"""Negative controls for portable count types; no production evaluator is replaced."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qualification.tests import test_consumer_vectors as runner


def run_bundle_case():
    result = unittest.TestResult()
    runner.ConsumerVectorTests("test_bundle_outcomes_match_portable_expectations").run(result)
    return result


class ConsumerVectorTypeTests(unittest.TestCase):
    def require_result(self, result, *, rejected):
        self.assertEqual(result.testsRun, 1)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.skipped, [])
        self.assertEqual(result.expectedFailures, [])
        self.assertEqual(result.unexpectedSuccesses, [])
        if rejected:
            self.assertGreater(len(result.failures), 0)
        else:
            self.assertEqual(result.failures, [])

    def test_wrong_report_count_types_fail_the_real_consumer_test(self):
        original = runner.evaluate
        for field in ("submitted", "eligible", "rejected"):
            for wrong_type in (bool, float):
                with self.subTest(field=field, wrong_type=wrong_type.__name__):
                    self.require_result(run_bundle_case(), rejected=False)

                    def changed_report(*args, field=field, wrong_type=wrong_type):
                        report = original(*args)
                        counts = report["coverage"]["capture_counts"]
                        # Preserve numerical equality, including the count of two
                        # in the reuse case. Only the representation changes.
                        if counts[field] in (0, 1):
                            counts[field] = wrong_type(counts[field])
                        return report

                    with patch.object(runner, "evaluate", changed_report):
                        self.require_result(run_bundle_case(), rejected=True)
                    self.require_result(run_bundle_case(), rejected=False)

    def test_wrong_fixture_count_types_fail_the_real_consumer_test(self):
        original = runner.CORPUS
        for field in ("submitted", "eligible", "rejected"):
            for wrong_type in (bool, float):
                with self.subTest(field=field, wrong_type=wrong_type.__name__):
                    self.require_result(run_bundle_case(), rejected=False)
                    corpus = json.loads(original.read_bytes())
                    counts = corpus["cases"][0]["expected"]["bundle"]["capture_counts"]
                    self.assertIn(counts[field], (0, 1))
                    counts[field] = wrong_type(counts[field])
                    with tempfile.TemporaryDirectory() as directory:
                        changed = Path(directory) / "vectors.json"
                        changed.write_text(json.dumps(corpus), encoding="utf-8")
                        with patch.object(runner, "CORPUS", changed):
                            self.require_result(run_bundle_case(), rejected=True)
                    self.require_result(run_bundle_case(), rejected=False)


if __name__ == "__main__":
    unittest.main()
