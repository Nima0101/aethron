"""Negative controls for the installed qualification acceptance checker."""

import copy
import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import qualification_consumer as consumer

CORPUS = Path(__file__).resolve().parents[1] / "qualification/fixtures/assessment-vectors-v1.json"
BUNDLE_CORPUS = CORPUS.with_name("consumer-vectors-v1.json")


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


class BundleConsumerTests(unittest.TestCase):
    def setUp(self):
        self.data = consumer.bundle_corpus(BUNDLE_CORPUS)
        self.cases = {case["id"]: case for case in self.data["cases"]}

    def test_replaced_or_oversized_corpus_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            for raw in (BUNDLE_CORPUS.read_bytes() + b" ", b"{}", b" " * 32769):
                path.write_bytes(raw)
                with self.assertRaisesRegex(ValueError, "^bundle_corpus_mismatch$"):
                    consumer.bundle_corpus(path)

    def test_all_vectors_preserve_frame_bytes_and_process_contract(self):
        from qualification.campaign_bundle_cli import _report
        from qualification.tests.test_campaign_bundle_cli import frame

        for case in self.data["cases"]:
            with self.subTest(case=case["id"]):
                args = consumer.bundle_arguments(self.data, case)
                raw = consumer.bundle_frame(args)
                self.assertEqual(raw, frame(*args))
                self.assertEqual(_report(io.BytesIO(raw)), consumer.evaluate_bundle(*args))
                output = (consumer.canonical(_report(io.BytesIO(raw))) + os.linesep).encode()
                status = 0 if case["expected"]["bundle"]["software_checks_passed"] else 1
                result = SimpleNamespace(returncode=status, stdout=output, stderr=b"")
                with patch.object(consumer.subprocess, "run", return_value=result) as run:
                    consumer.check_bundle_case(self.data, case)
                self.assertEqual(run.call_args.kwargs["input"], raw)
                self.assertEqual(
                    run.call_args.args[0],
                    [consumer.sys.executable, "-I", "-m", "qualification.campaign_bundle_cli"],
                )

    def test_numeric_substitutions_and_qualification_claims_are_rejected(self):
        case = self.cases["complete"]
        original = consumer.evaluate_bundle(*consumer.bundle_arguments(self.data, case))
        mutations = [
            (("software_checks_passed",), 1, "bundle_report_mismatch"),
            (("coverage", "capture_counts", "submitted"), True, "bundle_report_mismatch"),
            (("coverage", "capture_counts", "eligible"), 1.0, "bundle_report_mismatch"),
            (("plan_sha256",), "0" * 64, "bundle_plan_mismatch"),
        ]
        for key in (
            "artifact_bytes_verified",
            "artifact_authenticity_verified",
            "domain_verified",
            "procedure_verified",
            "physical_qualification_passed",
        ):
            for value in (True, 0):
                mutations.append(((key,), value, "bundle_qualification_claim"))
        for nested in ("coverage", "references"):
            mutations.append(
                ((nested, "physical_qualification_passed"), True, "bundle_qualification_claim")
            )
        for path, value, error in mutations:
            with self.subTest(path=path, value=value):
                report = copy.deepcopy(original)
                target = report
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with patch.object(consumer, "evaluate_bundle", return_value=report):
                    with self.assertRaisesRegex(AssertionError, "^" + error + "$"):
                        consumer.check_bundle_case(self.data, case)

    def test_artifact_failures_cannot_be_hidden_by_passing_bundle(self):
        case = self.cases["altered_artifact"]
        original = consumer.verify

        def changed(*args, **kwargs):
            report = original(*args, **kwargs)
            report["artifact_findings"] = []
            report["software_checks_passed"] = True
            report["artifact_bytes_verified"] = True
            return report

        with patch.object(consumer, "verify", side_effect=changed):
            with self.assertRaisesRegex(AssertionError, "^bundle_artifact_mismatch$"):
                consumer.check_bundle_case(self.data, case)

    def test_process_status_output_and_diagnostics_are_all_checked(self):
        case = self.cases["stale"]
        report = consumer.evaluate_bundle(*consumer.bundle_arguments(self.data, case))
        output = (consumer.canonical(report) + os.linesep).encode()
        for status, stdout, stderr in (
            (0, output, b""),
            (1, output + b"unexpected", b""),
            (1, output, b"unexpected"),
        ):
            with self.subTest(status=status, stderr=stderr):
                result = SimpleNamespace(returncode=status, stdout=stdout, stderr=stderr)
                with patch.object(consumer.subprocess, "run", return_value=result):
                    with self.assertRaisesRegex(AssertionError, "^bundle_process_mismatch$"):
                        consumer.check_bundle_case(self.data, case)


class MalformedConsumerTests(unittest.TestCase):
    def cases(self):
        assessment = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        data = consumer.bundle_corpus(BUNDLE_CORPUS)
        bundle = next(case for case in data["cases"] if case["id"] == "complete")
        return (
            (
                "qualification.assessment_cli",
                consumer.assessment_malformed_frames(consumer.arguments(assessment)),
                "invalid_qualification_assessment",
                17,
            ),
            (
                "qualification.campaign_bundle_cli",
                consumer.bundle_malformed_frames(consumer.bundle_arguments(data, bundle)),
                "invalid_campaign_bundle",
                13,
            ),
        )

    def test_all_frames_fail_before_source_evaluation(self):
        from qualification import assessment_cli, campaign_bundle_cli

        for (module, cases, _diagnostic, count), command in zip(
            self.cases(), (assessment_cli, campaign_bundle_cli)
        ):
            self.assertEqual(len(cases), count)
            self.assertEqual(len(set(cases.values())), count)
            with patch.object(command, "evaluate") as evaluate:
                for name, raw in cases.items():
                    with self.subTest(module=module, case=name):
                        with self.assertRaises(ValueError):
                            command._report(io.BytesIO(raw))
                evaluate.assert_not_called()

    def test_wrong_status_output_or_diagnostic_fails_at_any_case(self):
        for module, cases, diagnostic, _count in self.cases():
            fixed = (diagnostic + os.linesep).encode("ascii")
            good = SimpleNamespace(returncode=2, stdout=b"", stderr=fixed)
            for index, name in enumerate(cases):
                for status, stdout, stderr in (
                    (0, b"", fixed),
                    (1, b"", fixed),
                    (2, b"{}", fixed),
                    (2, b"", b""),
                    (2, b"", fixed + b"PRIVATE"),
                    (2, b"", b"different_error" + os.linesep.encode("ascii")),
                ):
                    with self.subTest(module=module, case=name, status=status, stderr=stderr):
                        bad = SimpleNamespace(returncode=status, stdout=stdout, stderr=stderr)
                        with patch.object(
                            consumer.subprocess, "run", side_effect=[good] * index + [bad]
                        ):
                            with self.assertRaises(AssertionError) as error:
                                consumer.check_malformed_frames(module, cases, diagnostic)
                        self.assertEqual(
                            str(error.exception),
                            "malformed_process_mismatch:" + module + ":" + name,
                        )

    def test_every_case_uses_isolated_binary_process_with_timeout(self):
        for module, cases, diagnostic, count in self.cases():
            result = SimpleNamespace(
                returncode=2, stdout=b"", stderr=(diagnostic + os.linesep).encode("ascii")
            )
            with patch.object(consumer.subprocess, "run", return_value=result) as run:
                self.assertEqual(consumer.check_malformed_frames(module, cases, diagnostic), count)
            self.assertEqual(run.call_count, count)
            for call, raw in zip(run.call_args_list, cases.values()):
                self.assertEqual(call.args[0], [consumer.sys.executable, "-I", "-m", module])
                self.assertEqual(
                    call.kwargs,
                    {"input": raw, "capture_output": True, "check": False, "timeout": 10},
                )


if __name__ == "__main__":
    unittest.main()
