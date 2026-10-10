"""Keep portable negative evidence distinct from a self-consistent replacement."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qualification.tests import test_consumer_vectors as runner


def run_consumer():
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(runner.ConsumerVectorTests)
    result = unittest.TestResult()
    suite.run(result)
    return result


class ConsumerCorpusBindingTests(unittest.TestCase):
    def require_result(self, result, *, rejected):
        self.assertEqual(result.testsRun, 3)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.skipped, [])
        self.assertEqual(result.expectedFailures, [])
        self.assertEqual(result.unexpectedSuccesses, [])
        if rejected:
            self.assertEqual(len(result.failures), 3)
        else:
            self.assertEqual(result.failures, [])

    def test_replacing_negative_cases_with_passing_inputs_is_rejected(self):
        original = runner.CORPUS.read_bytes()
        corpus = json.loads(original)
        complete = next(case for case in corpus["cases"] if case["id"] == "complete")
        negatives = sorted(runner.CASE_IDS - {"complete"})
        self.require_result(run_consumer(), rejected=False)
        for selected in [(name,) for name in negatives] + [tuple(negatives)]:
            with self.subTest(replaced=selected):
                changed = copy.deepcopy(corpus)
                for index, case in enumerate(changed["cases"]):
                    if case["id"] in selected:
                        replacement = copy.deepcopy(complete)
                        replacement["id"] = case["id"]
                        changed["cases"][index] = replacement
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "vectors.json"
                    path.write_text(json.dumps(changed), encoding="utf-8")
                    with patch.object(runner, "CORPUS", path):
                        self.require_result(run_consumer(), rejected=True)
        self.require_result(run_consumer(), rejected=False)

    def test_identical_bytes_at_another_path_still_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.json"
            path.write_bytes(runner.CORPUS.read_bytes())
            with patch.object(runner, "CORPUS", path):
                self.require_result(run_consumer(), rejected=False)


if __name__ == "__main__":
    unittest.main()
