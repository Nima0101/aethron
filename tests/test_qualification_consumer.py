"""Negative controls for the installed qualification acceptance checker."""

import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import qualification_consumer as consumer

CORPUS = Path(__file__).resolve().parents[1] / "qualification/fixtures/assessment-vectors-v1.json"


class QualificationConsumerTests(unittest.TestCase):
    def setUp(self):
        self.cases = {case["id"]: case for case in consumer.corpus(CORPUS)}

    def test_replaced_or_oversized_corpus_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            for raw in (CORPUS.read_bytes() + b" ", b"{}", b" " * 262145):
                path.write_bytes(raw)
                with self.assertRaisesRegex(ValueError, "^assessment_corpus_mismatch$"):
                    consumer.corpus(path)

    def test_library_numeric_substitution_does_not_pass(self):
        report = copy.deepcopy(self.cases["complete"]["expected_report"])
        report["software_checks_passed"] = 1
        with patch.object(consumer, "evaluate", return_value=report):
            with self.assertRaisesRegex(AssertionError, "^assessment_report_mismatch$"):
                consumer.check_case(self.cases["complete"])

    def test_missing_or_changed_fixed_error_is_rejected(self):
        with patch.object(consumer, "evaluate", return_value={}):
            with self.assertRaisesRegex(AssertionError, "^assessment_error_missing$"):
                consumer.check_case(self.cases["invalid_plan"])
        with patch.object(consumer, "evaluate", side_effect=ValueError("different_error")):
            with self.assertRaisesRegex(AssertionError, "^assessment_error_mismatch$"):
                consumer.check_case(self.cases["invalid_plan"])

    def test_process_status_output_and_diagnostics_are_all_checked(self):
        expected = consumer.canonical(self.cases["stale"]["expected_report"])
        from os import linesep

        output = (expected + linesep).encode("ascii")
        for status, stdout, stderr in (
            (0, output, b""),
            (1, output + b"unexpected", b""),
            (1, output, b"unexpected"),
        ):
            with self.subTest(status=status, stderr=stderr):
                result = SimpleNamespace(returncode=status, stdout=stdout, stderr=stderr)
                with patch.object(consumer.subprocess, "run", return_value=result):
                    with self.assertRaisesRegex(AssertionError, "^assessment_process_mismatch$"):
                        consumer.check_case(self.cases["stale"])


if __name__ == "__main__":
    unittest.main()
