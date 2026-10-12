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


class OpaqueArtifactConsumerTests(unittest.TestCase):
    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        self.args = consumer.arguments(self.case)
        for digest in self.args[1][0]["artifacts"]:
            self.args[1][0]["artifacts"][digest] += b"\r\n\x1a\x00\xffPRIVATE"
        self.report = consumer.evaluate(*self.args)
        self.output = (consumer.canonical(self.report) + os.linesep).encode("ascii")

    def test_binary_frame_matches_source_contract_without_mutating_corpus(self):
        from qualification.tests.test_assessment_cli import frame

        original = copy.deepcopy(self.case)
        result = SimpleNamespace(returncode=1, stdout=self.output, stderr=b"")
        with patch.object(consumer.subprocess, "run", return_value=result) as run:
            consumer.check_opaque_artifacts(self.case)
        self.assertEqual(self.case, original)
        self.assertEqual(
            run.call_args.args[0],
            [consumer.sys.executable, "-I", "-m", "qualification.assessment_cli"],
        )
        self.assertEqual(
            run.call_args.kwargs,
            {"input": frame(self.args), "capture_output": True, "check": False, "timeout": 10},
        )
        self.assertNotIn(b"PRIVATE", self.output)

    def test_library_cannot_hide_mismatch_or_claim_qualification(self):
        mutations = [
            (("submission_sha256",), self.case["expected_report"]["submission_sha256"]),
            (("captures", 0, "report", "artifact_findings"), []),
            (("captures", 0, "report", "artifact_counts", "supplied_bytes"), 14),
            (("captures", 0, "report", "artifact_counts", "mismatched"), True),
        ]
        for path in ((), ("captures", 0, "report")):
            for key in (
                "artifact_bytes_verified",
                "software_checks_passed",
                "artifact_authenticity_verified",
                "physical_qualification_passed",
            ):
                for value in (True, 0):
                    mutations.append(((*path, key), value))
        for path, value in mutations:
            with self.subTest(path=path, value=value):
                report = copy.deepcopy(self.report)
                target = report
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with patch.object(consumer, "evaluate", return_value=report):
                    with self.assertRaisesRegex(
                        AssertionError, "^opaque_assessment_report_mismatch$"
                    ):
                        consumer.check_opaque_artifacts(self.case)

    def test_process_cannot_translate_bytes_leak_payload_or_change_status(self):
        translated = copy.deepcopy(self.args)
        for digest, raw in translated[1][0]["artifacts"].items():
            translated[1][0]["artifacts"][digest] = raw.replace(b"\r\n", b"\n")
        translated_output = (
            consumer.canonical(consumer.evaluate(*translated)) + os.linesep
        ).encode("ascii")
        for status, stdout, stderr in (
            (0, self.output, b""),
            (2, b"", b"invalid_qualification_assessment" + os.linesep.encode("ascii")),
            (1, translated_output, b""),
            (1, self.output + b"PRIVATE", b""),
            (1, self.output, b"PRIVATE"),
        ):
            with self.subTest(status=status, stdout=stdout, stderr=stderr):
                result = SimpleNamespace(returncode=status, stdout=stdout, stderr=stderr)
                with patch.object(consumer.subprocess, "run", return_value=result):
                    with self.assertRaisesRegex(
                        AssertionError, "^opaque_assessment_process_mismatch$"
                    ):
                        consumer.check_opaque_artifacts(self.case)


class ExactLimitConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        cls.args = consumer.exact_limit_arguments(consumer.arguments(cls.case))
        cls.report = consumer.evaluate(*cls.args)
        cls.output = (consumer.canonical(cls.report) + os.linesep).encode("ascii")

    def test_frozen_limits_match_source_frame_and_isolated_process(self):
        from qualification import assessment_cli
        from qualification.tests.test_assessment_cli import frame

        plan, rows, domain, procedure, methods = self.args
        self.assertEqual([len(raw) for raw in (plan, domain, procedure)], [65536] * 3)
        self.assertEqual(len(methods), 48)
        self.assertTrue(all(raw == b"\xff" * 65536 for raw in methods.values()))
        self.assertEqual(len(rows), 64)
        for row in rows:
            self.assertEqual(row["case_id"], "a" * 64)
            self.assertEqual(len(row["manifest"]), 65536)
        self.assertEqual(len(rows[0]["artifacts"]), 15)
        self.assertEqual(
            [len(raw) for raw in rows[0]["artifacts"].values()], [1048576] * 4 + [0] * 11
        )
        self.assertTrue(all(row["artifacts"] == {} for row in rows[1:]))
        raw = frame(self.args)
        self.assertEqual(consumer.frame(self.args), raw)
        self.assertEqual(assessment_cli._report(io.BytesIO(raw)), self.report)
        original = copy.deepcopy(self.case)
        good = SimpleNamespace(returncode=1, stdout=self.output, stderr=b"")
        with patch.object(consumer.subprocess, "run", return_value=good) as run:
            self.assertEqual(consumer.check_exact_limits(self.case), 1)
        self.assertEqual(self.case, original)
        self.assertEqual(
            run.call_args.args[0],
            [consumer.sys.executable, "-I", "-m", "qualification.assessment_cli"],
        )
        self.assertEqual(
            run.call_args.kwargs,
            {"input": raw, "capture_output": True, "check": False, "timeout": 10},
        )

    def test_counts_and_negative_findings_cannot_disappear(self):
        mutations = [
            (("coverage", "findings"), []),
            (("domain", "findings"), []),
            (("methods", "procedure", "findings"), []),
            (("methods", "method_findings"), []),
            (("captures",), self.report["captures"][:-1]),
        ]
        for prefix in (("coverage", "capture_counts"), ("methods", "method_counts")):
            target = self.report[prefix[0]][prefix[1]]
            mutations.extend(((*prefix, key), True) for key in target)
        for index in range(64):
            prefix = ("captures", index)
            mutations.extend(
                [
                    ((*prefix, "capture_index"), -1),
                    ((*prefix, "findings"), ["capture_invalid"]),
                    ((*prefix, "report", "artifact_findings"), []),
                    ((*prefix, "report", "artifact_counts", "supplied_bytes"), True),
                    ((*prefix, "report", "declaration", "input_sha256"), "0" * 64),
                ]
            )
        for path, value in mutations:
            with self.subTest(path=path):
                report = copy.deepcopy(self.report)
                target = report
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with patch.object(consumer, "evaluate", return_value=report):
                    with self.assertRaisesRegex(
                        AssertionError, "^exact_limit_assessment_report_mismatch$"
                    ):
                        consumer.check_exact_limits(self.case)

    def test_each_report_layer_preserves_false_claims(self):
        for path in (
            (),
            ("coverage",),
            ("domain",),
            ("methods",),
            ("methods", "procedure"),
            ("captures", 0, "report"),
            ("captures", 63, "report"),
            ("captures", 0, "report", "declaration"),
            ("captures", 63, "report", "declaration"),
        ):
            original = self.report
            for key in path:
                original = original[key]
            for flag, current in original.items():
                if current is not False:
                    continue
                for value in (True, 0, None):
                    with self.subTest(path=path, flag=flag, value=value):
                        report = copy.deepcopy(self.report)
                        target = report
                        for key in path:
                            target = target[key]
                        if value is None:
                            del target[flag]
                        else:
                            target[flag] = value
                        with patch.object(consumer, "evaluate", return_value=report):
                            with self.assertRaisesRegex(
                                AssertionError, "^exact_limit_assessment_claim$"
                            ):
                                consumer.check_exact_limits(self.case)

    def test_process_cannot_reject_exact_limit_or_hide_negative_result(self):
        for status, stdout, stderr in (
            (0, self.output, b""),
            (2, b"", b"invalid_qualification_assessment" + os.linesep.encode("ascii")),
            (1, b"{}" + os.linesep.encode("ascii"), b""),
            (1, self.output + b"PRIVATE", b""),
            (1, self.output, b"PRIVATE"),
        ):
            with self.subTest(status=status, stderr=stderr):
                result = SimpleNamespace(returncode=status, stdout=stdout, stderr=stderr)
                with patch.object(consumer.subprocess, "run", return_value=result):
                    with self.assertRaisesRegex(
                        AssertionError, "^exact_limit_assessment_process_mismatch$"
                    ):
                        consumer.check_exact_limits(self.case)


class AggregateArtifactConsumerTests(unittest.TestCase):
    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        self.boundaries = consumer.aggregate_artifact_arguments(consumer.arguments(self.case))
        self.reports = {name: consumer.evaluate(*args) for name, args in self.boundaries.items()}

    def result(self, report):
        return SimpleNamespace(
            returncode=1,
            stdout=(consumer.canonical(report) + os.linesep).encode("ascii"),
            stderr=b"",
        )

    def test_complete_frames_reject_only_after_exceeding_aggregate_allowance(self):
        from qualification import assessment_cli
        from qualification.tests.test_assessment_cli import frame
        from qualification.tests.test_campaign_bundle_cli import NoReadPastHeader

        malformed = consumer.assessment_malformed_frames(consumer.arguments(self.case))
        for name, args in self.boundaries.items():
            with self.subTest(case=name):
                rows = args[1]
                self.assertEqual(len(rows), 2 if name == "single_capture" else 5)
                self.assertEqual(
                    sum(len(raw) for r in rows for raw in r["artifacts"].values()), 4194304
                )
                self.assertTrue(
                    all(len(raw) <= 1048576 for r in rows for raw in r["artifacts"].values())
                )
                self.assertEqual(rows[-1]["artifacts"], {"0" * 64: b""})
                if name == "across_captures":
                    self.assertTrue(
                        all(row["artifacts"] == rows[0]["artifacts"] for row in rows[:-1])
                    )
                self.assertEqual(consumer.frame(args), frame(args))
                self.assertEqual(
                    assessment_cli._report(io.BytesIO(frame(args))), self.reports[name]
                )
                oversized = copy.deepcopy(args)
                oversized[1][-1]["artifacts"]["0" * 64] = b"x"
                raw = malformed["aggregate_" + name + "_frame"]
                self.assertEqual(raw, frame(oversized))
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_assessment$"):
                    consumer.evaluate(*oversized)
                # Removing only the final byte leaves its length header intact;
                # the parser must reject before trying to read that byte.
                with patch.object(assessment_cli, "evaluate") as evaluate:
                    with self.assertRaises(ValueError):
                        assessment_cli._report(NoReadPastHeader(raw[:-1]))
                    evaluate.assert_not_called()

    def test_exact_limit_uses_binary_isolated_process_and_preserves_corpus(self):
        from qualification.tests.test_assessment_cli import frame

        original = copy.deepcopy(self.case)
        with patch.object(
            consumer.subprocess, "run", side_effect=[self.result(r) for r in self.reports.values()]
        ) as run:
            self.assertEqual(consumer.check_aggregate_artifacts(self.case), 2)
        self.assertEqual(self.case, original)
        self.assertEqual(run.call_count, 2)
        for call, args in zip(run.call_args_list, self.boundaries.values()):
            self.assertEqual(
                call.args[0], [consumer.sys.executable, "-I", "-m", "qualification.assessment_cli"]
            )
            self.assertEqual(
                call.kwargs,
                {"input": frame(args), "capture_output": True, "check": False, "timeout": 10},
            )

    def test_counts_negative_evidence_and_false_claims_are_checked_for_each_capture(self):
        for index, (name, original) in enumerate(self.reports.items()):
            mutations = []
            for i in range(len(original["captures"])):
                prefix = ("captures", i, "report")
                mutations.append(((*prefix, "artifact_findings"), [], "report_mismatch"))
                for key in original["captures"][i]["report"]["artifact_counts"]:
                    mutations.append(((*prefix, "artifact_counts", key), True, "report_mismatch"))
            for prefix in (
                (),
                *(("captures", i, "report") for i in range(len(original["captures"]))),
            ):
                for key in (
                    "artifact_bytes_verified",
                    "software_checks_passed",
                    "artifact_authenticity_verified",
                    "physical_qualification_passed",
                ):
                    for value in (True, 0):
                        mutations.append(((*prefix, key), value, "claim"))
            for path, value, error in mutations:
                with self.subTest(case=name, path=path, value=value):
                    report = copy.deepcopy(original)
                    target = report
                    for key in path[:-1]:
                        target = target[key]
                    target[path[-1]] = value
                    preceding = list(self.reports.values())[:index]
                    with (
                        patch.object(consumer, "evaluate", side_effect=[*preceding, report]),
                        patch.object(
                            consumer.subprocess,
                            "run",
                            side_effect=[self.result(r) for r in preceding],
                        ),
                    ):
                        with self.assertRaisesRegex(
                            AssertionError, "^aggregate_assessment_" + error + ":" + name + "$"
                        ):
                            consumer.check_aggregate_artifacts(self.case)

    def test_process_cannot_reject_exact_limit_hide_findings_or_change_status(self):
        for index, (name, report) in enumerate(self.reports.items()):
            good = self.result(report)
            for status, stdout, stderr in (
                (0, good.stdout, b""),
                (2, b"", b"invalid_qualification_assessment" + os.linesep.encode("ascii")),
                (1, b"{}" + os.linesep.encode("ascii"), b""),
                (1, good.stdout + b"PRIVATE", b""),
                (1, good.stdout, b"PRIVATE"),
            ):
                with self.subTest(case=name, status=status, stderr=stderr):
                    preceding = [self.result(r) for r in list(self.reports.values())[:index]]
                    bad = SimpleNamespace(returncode=status, stdout=stdout, stderr=stderr)
                    with patch.object(consumer.subprocess, "run", side_effect=[*preceding, bad]):
                        with self.assertRaisesRegex(
                            AssertionError, "^aggregate_assessment_process_mismatch:" + name + "$"
                        ):
                            consumer.check_aggregate_artifacts(self.case)


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
                58,
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

    def test_oversized_complete_frames_have_independent_bounds_and_repairs(self):
        from qualification import assessment_cli
        from qualification.tests.test_assessment_cli import frame
        from qualification.tests.test_campaign_bundle_cli import NoReadPastHeader

        case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        original = consumer.arguments(case)
        _module, cases, _diagnostic, _count = self.cases()[0]
        limits = {
            "plan": ((0,), 65536),
            "domain": ((2,), 65536),
            "procedure": ((3,), 65536),
            "manifest": ((1, 0, "manifest"), 65536),
            "method_count": ((4,), 48),
            "method": ((4,), 65536),
            "capture_count": ((1,), 64),
            "artifact_count": ((1, 0, "artifacts"), 15),
            "artifact": ((1, 0, "artifacts"), 1048576),
        }
        for name, (path, limit) in limits.items():
            with self.subTest(case=name):
                args = list(copy.deepcopy(original))
                target = args
                for key in path[:-1]:
                    target = target[key]
                key = path[-1]
                if name in ("method_count", "artifact_count"):
                    value = {f"{i:064x}": b"" for i in range(limit + 1)}
                    repaired = dict(list(value.items())[:-1])
                elif name in ("method", "artifact"):
                    value = {"a" * 64: b"\xff" * (limit + 1)}
                    repaired = {"a" * 64: b"\xff" * limit}
                elif name == "capture_count":
                    value = [copy.deepcopy(original[1][0]) for _ in range(limit + 1)]
                    repaired = value[:-1]
                else:
                    value = target[key] + b" " * (limit + 1 - len(target[key]))
                    repaired = value[:-1]
                target[key] = value
                raw = cases["oversized_" + name + "_frame"]
                self.assertEqual(raw, frame(args))
                self.assertLess(
                    sum(len(b) for row in args[1] for b in row["artifacts"].values()),
                    4194304,
                )
                header = cases["oversized_" + name]
                self.assertTrue(raw.startswith(header))
                # Fail before reading the oversized field, even with a complete
                # remainder available. The guarded stream catches excess reads.
                with patch.object(assessment_cli, "evaluate") as evaluate:
                    for stream in (io.BytesIO(raw), NoReadPastHeader(header)):
                        with self.assertRaises(ValueError):
                            assessment_cli._report(stream)
                    evaluate.assert_not_called()
                # Only this field is reduced to its exact bound. Evaluation
                # must see every later field unchanged and retain non-authority.
                target[key] = repaired
                sentinel = object()
                with patch.object(assessment_cli, "evaluate", return_value=sentinel) as evaluate:
                    self.assertIs(assessment_cli._report(io.BytesIO(frame(args))), sentinel)
                    evaluate.assert_called_once_with(*args)
                report = assessment_cli._report(io.BytesIO(frame(args)))
                self.assertIs(report["physical_qualification_passed"], False)
                self.assertEqual(report, consumer.evaluate(*args))

    def test_bad_keys_fail_before_value_read_and_have_complete_envelopes(self):
        from qualification import assessment_cli
        from qualification.tests.test_campaign_bundle_cli import NoReadPastHeader

        _module, cases, _diagnostic, _count = self.cases()[0]
        headers = {name: raw for name, raw in cases.items() if name.endswith("_key_header")}
        self.assertEqual(len(headers), 8)
        for name, header in headers.items():
            with self.subTest(case=name):
                with patch.object(assessment_cli, "evaluate") as evaluate:
                    with self.assertRaises(ValueError):
                        assessment_cli._report(NoReadPastHeader(header))
                    evaluate.assert_not_called()
                full = cases[name.removesuffix("_header") + "_frame"]
                self.assertTrue(full.startswith(header))
                # Repair only the offending key; the otherwise complete frame
                # must reach evaluation, proving EOF is not the rejection cause.
                repaired = header[:-64] + b"b" * 64 + full[len(header) :]
                sentinel = object()
                with patch.object(assessment_cli, "evaluate", return_value=sentinel) as evaluate:
                    self.assertIs(assessment_cli._report(io.BytesIO(repaired)), sentinel)
                    evaluate.assert_called_once()

    def test_invalid_scalars_have_complete_frames_and_single_field_repairs(self):
        from qualification import assessment_cli
        from qualification.tests.test_assessment_cli import frame

        case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        original = consumer.arguments(case)
        _module, cases, _diagnostic, _count = self.cases()[0]
        values = {
            "now_ms": {
                "true": True,
                "false": False,
                "float": 1050.0,
                "string": "1050",
                "null": None,
                "array": [],
                "object": {},
                "negative": -1,
                "above_maximum": 2**53 - 999,
                "overflow": 2**53,
                "infinity": float("inf"),
            },
            "case_id": {"empty": "", "space": "PRIVATE name", "path": "a/b"},
        }
        names = set()
        for field, invalid in values.items():
            for label, value in invalid.items():
                name = ("instant" if field == "now_ms" else field) + "_" + label + "_frame"
                names.add(name)
                with self.subTest(case=name):
                    args = copy.deepcopy(original)
                    args[1][0][field] = value
                    # Independent source-test encoder proves that all later
                    # fields are present and only the selected scalar changed.
                    self.assertEqual(cases[name], frame(args))
                    with patch.object(assessment_cli, "evaluate") as evaluate:
                        with self.assertRaises(ValueError):
                            assessment_cli._report(io.BytesIO(cases[name]))
                        evaluate.assert_not_called()
                    args[1][0][field] = original[1][0][field]
                    sentinel = object()
                    with patch.object(
                        assessment_cli, "evaluate", return_value=sentinel
                    ) as evaluate:
                        self.assertIs(assessment_cli._report(io.BytesIO(frame(args))), sentinel)
                        evaluate.assert_called_once_with(*original)
        self.assertEqual(
            names,
            {name for name in cases if name.startswith(("instant_", "case_id_"))},
        )

    def test_valid_scalar_boundaries_reach_evaluation_without_coercion(self):
        from qualification import assessment_cli

        case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        for instant in (0, 2**53 - 1000):
            for name in ("a", "Az09_-" + "a" * 58):
                with self.subTest(instant=instant, name=name):
                    args = consumer.arguments(case)
                    args[1][0].update(now_ms=instant, case_id=name)
                    with patch.object(assessment_cli, "evaluate") as evaluate:
                        assessment_cli._report(io.BytesIO(consumer.frame(args)))
                        evaluate.assert_called_once_with(*args)
                        self.assertIs(type(evaluate.call_args.args[1][0]["now_ms"]), int)

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
