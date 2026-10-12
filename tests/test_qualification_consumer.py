"""Negative controls for the installed qualification acceptance checker."""

import copy
import errno
import hashlib
import io
import json
import os
import struct
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


class DeclarationConsumerTests(unittest.TestCase):
    def setUp(self):
        self.cases = {
            case["id"]: case
            for case in consumer.corpus(CORPUS)
            if case["id"] in ("complete", "stale")
        }

    def report(self, case):
        return case["expected_report"]["captures"][0]["report"]["declaration"]

    def result(self, case, report=None):
        if report is None:
            report = self.report(case)
        return SimpleNamespace(
            returncode=0 if case["id"] == "complete" else 1,
            stdout=(consumer.canonical(report) + os.linesep).encode("ascii"),
            stderr=b"",
        )

    def mutations(self, case):
        report = self.report(case)
        for key, value in (
            ("version", True),
            ("input_sha256", "0" * 64),
            ("declaration_checks_passed", int(report["declaration_checks_passed"])),
            ("sensor_count", 2.0),
            ("record_count", True),
            ("findings", ["capture_stale"] if case["id"] == "complete" else []),
            ("artifacts_verified", True),
            ("artifacts_verified", 0),
            ("physical_qualification_passed", True),
            ("physical_qualification_passed", 0),
            ("physical_status", "qualified"),
        ):
            changed = copy.deepcopy(report)
            changed[key] = value
            yield key, changed
        for key in report["evidence_counts"]:
            changed = copy.deepcopy(report)
            changed["evidence_counts"][key] = float(changed["evidence_counts"][key])
            yield "evidence_counts:" + key, changed

    def test_pinned_reports_and_instants_reach_both_isolated_cli_forms(self):
        for name, instant in (("complete", 1050), ("stale", 1151)):
            with self.subTest(case=name):
                case = self.cases[name]
                original = copy.deepcopy(case)
                raw = bytes.fromhex(case["captures"][0]["manifest_hex"])
                with (
                    patch.object(consumer, "validate", wraps=consumer.validate) as validate,
                    patch.object(consumer.subprocess, "run", return_value=self.result(case)) as run,
                ):
                    self.assertEqual(consumer.check_declaration(case), 2)
                validate.assert_called_once_with(raw, now_ms=instant)
                self.assertEqual(run.call_count, 2)
                for call, args in zip(
                    run.call_args_list, (["--now-ms", str(instant)], ["--now-ms=" + str(instant)])
                ):
                    self.assertEqual(
                        call.args[0],
                        [consumer.sys.executable, "-I", "-m", "qualification", *args],
                    )
                    self.assertEqual(
                        call.kwargs,
                        {"input": raw, "capture_output": True, "check": False, "timeout": 10},
                    )
                self.assertEqual(case, original)

    def test_library_cannot_change_types_findings_or_qualification_flags(self):
        for case in self.cases.values():
            for name, report in self.mutations(case):
                with self.subTest(case=case["id"], mutation=name):
                    with (
                        patch.object(consumer, "validate", return_value=report),
                        patch.object(consumer.subprocess, "run") as run,
                    ):
                        with self.assertRaisesRegex(
                            AssertionError, "^declaration_report_mismatch$"
                        ):
                            consumer.check_declaration(case)
                        run.assert_not_called()

    def test_each_cli_form_rejects_changed_typed_report(self):
        for case in self.cases.values():
            for name, report in self.mutations(case):
                for index in range(2):
                    with self.subTest(case=case["id"], mutation=name, form=index):
                        results = [self.result(case), self.result(case)]
                        results[index] = self.result(case, report)
                        with patch.object(consumer.subprocess, "run", side_effect=results):
                            with self.assertRaisesRegex(
                                AssertionError, "^declaration_process_mismatch$"
                            ):
                                consumer.check_declaration(case)

    def test_each_cli_form_checks_status_bytes_and_stderr(self):
        for case in self.cases.values():
            good = self.result(case)
            for key, value in (
                ("returncode", 1 - good.returncode),
                ("returncode", 2),
                ("stdout", good.stdout.rstrip(b"\r\n")),
                ("stdout", good.stdout + b"PRIVATE"),
                ("stdout", b""),
                ("stderr", b"PRIVATE"),
            ):
                for index in range(2):
                    with self.subTest(case=case["id"], mutation=key, value=value, form=index):
                        bad = copy.copy(good)
                        setattr(bad, key, value)
                        results = [good, good]
                        results[index] = bad
                        with patch.object(consumer.subprocess, "run", side_effect=results):
                            with self.assertRaisesRegex(
                                AssertionError, "^declaration_process_mismatch$"
                            ):
                                consumer.check_declaration(case)


class DeclarationCollectionBoundaryTests(unittest.TestCase):
    generate = staticmethod(consumer.declaration_collection_boundaries)
    check = staticmethod(consumer.check_declaration_collection_boundaries)
    diagnostic = "declaration_collection_"
    count = 7

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        original = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        self.cases = {}
        # Construct independent documents and literal semantic expectations;
        # neither the installed generator nor validator supplies this oracle.
        for count in (1, 5):
            for empty in (False, True):
                doc = copy.deepcopy(original)
                sensors = doc["rig"]["sensors"][:1] if count == 1 else doc["rig"]["sensors"]
                if count == 5:
                    for kind in ("rgb", "radar", "nir"):
                        sensor = copy.deepcopy(sensors[0])
                        sensor.update(id=kind, kind=kind)
                        sensors.append(sensor)
                doc["rig"]["sensors"] = sensors
                digest = hashlib.sha256(self.encode(doc["rig"])).hexdigest()
                doc["records"] = []
                if not empty:
                    for sensor in sensors:
                        templates = [
                            row for row in original["records"] if row["sensor_id"] == sensor["id"]
                        ] or original["records"][:3]
                        for template in templates:
                            record = copy.deepcopy(template)
                            record.update(sensor_id=sensor["id"], rig_sha256=digest)
                            doc["records"].append(record)
                findings = (
                    ["missing_calibration", "missing_clock", "missing_environment"] if empty else []
                )
                name = str(count) + "_sensors_" + ("empty" if empty else "complete")
                self.save(name, doc, count, 0 if empty else count * 3, findings)
        for name, capture, calibration, findings in (
            ("equal_capture", True, False, []),
            ("equal_calibration", False, True, ["calibration_interval"]),
            ("equal_both", True, True, []),
        ):
            doc = copy.deepcopy(original)
            if capture:
                doc["capture"]["start_ms"] = 1050
            if calibration:
                for record in doc["records"]:
                    if record["kind"] == "calibration":
                        record["data"].update(valid_from_ms=1050, valid_until_ms=1050)
            self.save(name, doc, 2, 6, findings)

    def encode(self, value):
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")

    def save(self, name, doc, sensors, records, findings):
        raw = self.encode(doc)
        report = {
            "version": 1,
            "input_sha256": hashlib.sha256(raw).hexdigest(),
            "declaration_checks_passed": not findings,
            "sensor_count": sensors,
            "record_count": records,
            "evidence_counts": {"synthetic": records, "recorded": 0, "external_unverified": 0},
            "findings": findings,
            "artifacts_verified": False,
            "physical_qualification_passed": False,
            "physical_status": "blocked_external_evidence_and_review",
        }
        self.cases[name] = raw, report

    def result(self, report):
        return SimpleNamespace(
            returncode=0 if report["declaration_checks_passed"] else 1,
            stdout=self.encode(report) + os.linesep.encode("ascii"),
            stderr=b"",
        )

    def test_independent_documents_reports_and_isolated_binary_calls(self):
        original = copy.deepcopy(self.case)
        self.assertEqual(self.generate(self.case), self.cases)
        with patch.object(
            consumer.subprocess, "run", side_effect=[self.result(r) for _, r in self.cases.values()]
        ) as run:
            self.assertEqual(self.check(self.case), self.count)
        self.assertEqual(run.call_count, self.count)
        for call, (raw, _) in zip(run.call_args_list, self.cases.values()):
            self.assertLessEqual(len(raw), 65536)
            self.assertEqual(
                call.args[0],
                [consumer.sys.executable, "-I", "-m", "qualification", "--now-ms", "1050"],
            )
            self.assertEqual(
                call.kwargs,
                {"input": raw, "capture_output": True, "check": False, "timeout": 10},
            )
        self.assertEqual(self.case, original)

    def test_every_boundary_rejects_corrupted_library_and_process_reports(self):
        reports = [report for _, report in self.cases.values()]
        for index, (name, (_, report)) in enumerate(self.cases.items()):
            for key, value in (
                ("version", True),
                ("input_sha256", "0" * 64),
                ("sensor_count", float(report["sensor_count"])),
                ("record_count", float(report["record_count"])),
                ("declaration_checks_passed", int(report["declaration_checks_passed"])),
                ("findings", [] if report["findings"] else ["capture_stale"]),
                ("artifacts_verified", True),
                ("artifacts_verified", 0),
                ("physical_qualification_passed", True),
                ("physical_qualification_passed", 0),
                ("physical_status", "qualified"),
                *(
                    ("evidence_counts", dict(report["evidence_counts"], **{kind: float(count)}))
                    for kind, count in report["evidence_counts"].items()
                ),
            ):
                changed = copy.deepcopy(report)
                changed[key] = value
                for mode in ("report", "process"):
                    with self.subTest(case=name, field=key, mode=mode):
                        library = copy.deepcopy(reports)
                        results = [self.result(item) for item in reports]
                        if mode == "report":
                            library[index] = changed
                        else:
                            results[index].stdout = self.encode(changed) + os.linesep.encode()
                        with (
                            patch.object(consumer, "validate", side_effect=library),
                            patch.object(consumer.subprocess, "run", side_effect=results),
                        ):
                            with self.assertRaisesRegex(
                                AssertionError,
                                "^" + self.diagnostic + mode + "_mismatch:" + name + "$",
                            ):
                                self.check(self.case)

    def test_every_boundary_checks_exit_status_stdout_and_stderr(self):
        good = [self.result(report) for _, report in self.cases.values()]
        for index, name in enumerate(self.cases):
            for key, value in (
                ("returncode", 1 - good[index].returncode),
                ("returncode", 2),
                ("stdout", b""),
                ("stdout", good[index].stdout.rstrip(b"\r\n")),
                ("stdout", good[index].stdout + b"PRIVATE"),
                ("stderr", b"PRIVATE"),
            ):
                with self.subTest(case=name, field=key):
                    results = copy.deepcopy(good)
                    setattr(results[index], key, value)
                    with patch.object(consumer.subprocess, "run", side_effect=results):
                        with self.assertRaisesRegex(
                            AssertionError, "^" + self.diagnostic + "process_mismatch:" + name + "$"
                        ):
                            self.check(self.case)


class DeclarationClockBoundaryTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_clock_boundaries)
    check = staticmethod(consumer.check_declaration_clock_boundaries)
    diagnostic = "declaration_clock_"
    count = 12

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        original = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        self.cases = {}
        # Literal boundary expectations are independent of the installed generator.
        for name, left, right, findings in (
            ("reference_positive_50", (49, 1), (49, 1), []),
            ("reference_positive_51", (50, 1), (50, 1), ["clock_reference_skew"]),
            ("reference_negative_50", (-49, 1), (-49, 1), []),
            ("reference_negative_51", (-50, 1), (-50, 1), ["clock_reference_skew"]),
            ("pair_offset_forward_50", (-24, 1), (24, 1), []),
            ("pair_offset_forward_51", (-24, 1), (24, 2), ["clock_pair_skew"]),
            ("pair_offset_reverse_50", (24, 1), (-24, 1), []),
            ("pair_offset_reverse_51", (24, 2), (-24, 1), ["clock_pair_skew"]),
            ("pair_uncertainty_forward_50", (0, 20), (0, 30), []),
            ("pair_uncertainty_forward_51", (0, 20), (0, 31), ["clock_pair_skew"]),
            ("pair_uncertainty_reverse_50", (0, 30), (0, 20), []),
            ("pair_uncertainty_reverse_51", (0, 31), (0, 20), ["clock_pair_skew"]),
        ):
            doc = copy.deepcopy(original)
            for index, (offset, uncertainty) in ((1, left), (4, right)):
                self.assertEqual(doc["records"][index]["kind"], "clock")
                doc["records"][index]["data"] = {
                    "at_ms": 1050,
                    "offset_ms": offset,
                    "uncertainty_ms": uncertainty,
                }
            self.save(name, doc, 2, 6, findings)


class DeclarationFreshnessBoundaryTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_freshness_boundaries)
    check = staticmethod(consumer.check_declaration_freshness_boundaries)
    diagnostic = "declaration_freshness_"
    count = 16

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        original = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        self.cases = {}
        # Literal times and findings independently pin the two distinct age
        # windows and inclusive capture endpoints; no validator-derived oracle.
        for name, start, end, findings in (
            ("capture_age_0", 1000, 1050, []),
            ("capture_age_100", 900, 950, []),
            ("capture_age_101", 899, 949, ["capture_stale"]),
            ("capture_age_-1", 1001, 1051, ["capture_future"]),
        ):
            doc = copy.deepcopy(original)
            doc["capture"].update(start_ms=start, end_ms=end)
            for index in (1, 2, 4, 5):
                doc["records"][index]["data"]["at_ms"] = end
            self.save(name, doc, 2, 6, findings)
        for kind, index in (("clock", 1), ("environment", 2)):
            self.assertEqual(original["records"][index]["kind"], kind)
            for suffix, start, at_ms, findings in (
                ("age_100", 900, 950, []),
                ("age_101", 900, 949, ["record_stale"]),
                ("start_ms_equal", 1000, 1000, []),
                ("start_ms_outside", 1000, 999, ["record_outside_capture"]),
                ("end_ms_equal", 1000, 1050, []),
                ("end_ms_outside", 1000, 1051, ["record_outside_capture"]),
            ):
                doc = copy.deepcopy(original)
                doc["capture"]["start_ms"] = start
                doc["records"][index]["data"]["at_ms"] = at_ms
                self.save(kind + "_" + suffix, doc, 2, 6, findings)


class DeclarationDomainBoundaryTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_domain_boundaries)
    check = staticmethod(consumer.check_declaration_domain_boundaries)
    diagnostic = "declaration_domain_"
    count = 26

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        original = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        self.cases = {}
        # Literal times/findings independently pin coverage and domain handling
        # for each sensor, without obtaining expectations from the validator.
        for base in (0, 3):
            sensor_id = original["records"][base]["sensor_id"]
            self.assertEqual(original["records"][base]["kind"], "calibration")
            for field, value, suffix, findings in (
                ("valid_from_ms", 1000, "equal", []),
                ("valid_from_ms", 1001, "outside", ["calibration_interval"]),
                ("valid_until_ms", 1050, "equal", []),
                ("valid_until_ms", 1049, "outside", ["calibration_interval"]),
            ):
                doc = copy.deepcopy(original)
                doc["records"][base]["data"][field] = value
                self.save(sensor_id + "_" + field + "_" + suffix, doc, 2, 6, findings)
            for offset, kind, changes, local_findings in (
                (
                    0,
                    "calibration",
                    {"valid_from_ms": 0, "valid_until_ms": 0},
                    ["calibration_interval"],
                ),
                (
                    1,
                    "clock",
                    {"at_ms": 0, "offset_ms": 100, "uncertainty_ms": 1},
                    [
                        "clock_pair_skew",
                        "clock_reference_skew",
                        "record_outside_capture",
                        "record_stale",
                    ],
                ),
                (2, "environment", {"at_ms": 0}, ["record_outside_capture", "record_stale"]),
            ):
                for mode, findings in (
                    ("comparable", local_findings),
                    ("foreign", ["clock_domain_mismatch"]),
                    ("foreign_unbound", ["clock_domain_mismatch", "rig_binding_mismatch"]),
                ):
                    doc = copy.deepcopy(original)
                    record = doc["records"][base + offset]
                    self.assertEqual(record["kind"], kind)
                    record["data"].update(changes)
                    if mode in ("foreign", "foreign_unbound"):
                        record["clock_domain"] = "foreign_clock"
                    if mode == "foreign_unbound":
                        record["rig_sha256"] = "0" * 64
                    self.save(sensor_id + "_" + kind + "_" + mode, doc, 2, 6, findings)


class DeclarationArgumentConsumerTests(unittest.TestCase):
    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        self.raw = bytes.fromhex(self.case["captures"][0]["manifest_hex"])
        self.fixed = ("invalid_qualification_manifest" + os.linesep).encode("ascii")
        self.good = SimpleNamespace(returncode=2, stdout=b"", stderr=self.fixed)

    def test_complete_manifest_and_isolated_argument_vectors(self):
        original = copy.deepcopy(self.case)
        self.assertIs(consumer.validate(self.raw, now_ms=1050)["declaration_checks_passed"], True)
        self.assertEqual(consumer.validate(self.raw, now_ms=1151)["findings"], ["capture_stale"])
        args = list(consumer.invalid_declaration_arguments().values())
        self.assertEqual(len(args), 29)
        self.assertEqual(len({tuple(item) for item in args}), 29)
        for required in (
            ["--now-ms", "1151", "--now-ms", "1050"],
            ["--now-ms=1050", "--now-ms=1151"],
            ["--now-ms", "1050", "--now-ms=1050"],
            ["--now-ms=1151", "--now-ms", "1050"],
            [],
            ["--now-ms"],
            ["--now-ms="],
            ["--now-ms", "1050", "PRIVATE path with spaces"],
            ["--now-ms", "1050", ""],
            ["--now-ms", "1050", "--", "PRIVATE"],
            ["--now-ms", "1050", "--PRIVATE"],
        ):
            self.assertIn(required, args)
        for option in ("--n", "--now", "--now-m"):
            self.assertIn([option, "1050"], args)
            self.assertIn([option + "=1050"], args)
        for value in (
            "PRIVATE instant with spaces",
            "1.5",
            "NaN",
            "True",
            "-1",
            "9007199254739993",
        ):
            self.assertIn(["--now-ms", value], args)
            self.assertIn(["--now-ms=" + value], args)
        with patch.object(consumer.subprocess, "run", return_value=self.good) as run:
            self.assertEqual(consumer.check_declaration_arguments(self.case), 29)
        self.assertEqual(run.call_count, 29)
        for call, argv in zip(run.call_args_list, args):
            self.assertEqual(
                call.args[0], [consumer.sys.executable, "-I", "-m", "qualification", *argv]
            )
            self.assertEqual(
                call.kwargs,
                {"input": self.raw, "capture_output": True, "check": False, "timeout": 10},
            )
        self.assertEqual(self.case, original)

    def test_source_cli_rejects_every_case_with_valid_manifest(self):
        from qualification import __main__ as cli

        for name, args in consumer.invalid_declaration_arguments().items():
            with self.subTest(case=name):
                stdout, stderr = io.StringIO(), io.StringIO()
                with (
                    patch.object(cli.sys, "argv", ["qualification", *args]),
                    patch.object(cli.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(self.raw))),
                    patch.object(cli.sys, "stdout", stdout),
                    patch.object(cli.sys, "stderr", stderr),
                ):
                    status = cli.main()
                self.assertEqual(
                    (status, stdout.getvalue(), stderr.getvalue()),
                    (2, "", "invalid_qualification_manifest\n"),
                )

    def test_each_argument_case_checks_status_stdout_and_fixed_diagnostic(self):
        for index, name in enumerate(consumer.invalid_declaration_arguments()):
            for status, stdout, stderr in (
                (0, b"", self.fixed),
                (1, b"", self.fixed),
                (2, self.raw, self.fixed),
                (2, b"PRIVATE", self.fixed),
                (2, b"", b""),
                (2, b"", self.fixed + b"PRIVATE"),
                (2, b"", self.raw),
                (2, b"usage: qualification --help", b""),
                (2, b"", b"usage: qualification --help"),
            ):
                with self.subTest(case=name, status=status, stdout=stdout, stderr=stderr):
                    bad = SimpleNamespace(returncode=status, stdout=stdout, stderr=stderr)
                    with patch.object(
                        consumer.subprocess, "run", side_effect=[self.good] * index + [bad]
                    ):
                        with self.assertRaises(AssertionError) as error:
                            consumer.check_declaration_arguments(self.case)
                    self.assertEqual(
                        str(error.exception), "declaration_argument_process_mismatch:" + name
                    )


class DeclarationInputConsumerTests(unittest.TestCase):
    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        self.raw = bytes.fromhex(self.case["captures"][0]["manifest_hex"])
        self.padded = self.raw + b" " * (65536 - len(self.raw))
        self.report = copy.deepcopy(
            self.case["expected_report"]["captures"][0]["report"]["declaration"]
        )
        self.report["input_sha256"] = hashlib.sha256(self.padded).hexdigest()
        self.good = SimpleNamespace(
            returncode=0,
            stdout=(consumer.canonical(self.report) + os.linesep).encode("ascii"),
            stderr=b"",
        )
        self.fixed = ("invalid_qualification_manifest" + os.linesep).encode("ascii")
        self.rejected = SimpleNamespace(returncode=2, stdout=b"", stderr=self.fixed)

    def test_exact_boundary_keeps_pinned_report_and_binary_process_contract(self):
        original = copy.deepcopy(self.case)
        with (
            patch.object(consumer, "validate", wraps=consumer.validate) as validate,
            patch.object(consumer.subprocess, "run", return_value=self.good) as run,
        ):
            self.assertEqual(consumer.check_declaration_input_boundary(self.case), 1)
        validate.assert_called_once_with(self.padded, now_ms=1050)
        run.assert_called_once_with(
            [consumer.sys.executable, "-I", "-m", "qualification", "--now-ms", "1050"],
            input=self.padded,
            capture_output=True,
            check=False,
            timeout=10,
        )
        self.assertNotEqual(self.report["input_sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(self.case, original)

    def test_exact_boundary_cannot_lose_digest_types_or_negative_claims(self):
        for key, value in (
            ("input_sha256", hashlib.sha256(self.raw).hexdigest()),
            ("record_count", float(self.report["record_count"])),
            ("declaration_checks_passed", 1),
            ("findings", ["capture_stale"]),
            ("artifacts_verified", True),
            ("physical_qualification_passed", True),
        ):
            changed = copy.deepcopy(self.report)
            changed[key] = value
            with self.subTest(field=key):
                with patch.object(consumer, "validate", return_value=changed):
                    with self.assertRaisesRegex(
                        AssertionError, "^declaration_boundary_report_mismatch$"
                    ):
                        consumer.check_declaration_input_boundary(self.case)
                bad = copy.copy(self.good)
                bad.stdout = (consumer.canonical(changed) + os.linesep).encode("ascii")
                with patch.object(consumer.subprocess, "run", return_value=bad):
                    with self.assertRaisesRegex(
                        AssertionError, "^declaration_boundary_process_mismatch$"
                    ):
                        consumer.check_declaration_input_boundary(self.case)
        for key, value in (
            ("returncode", 1),
            ("returncode", 2),
            ("stdout", b""),
            ("stderr", b"PRIVATE"),
        ):
            bad = copy.copy(self.good)
            setattr(bad, key, value)
            with patch.object(consumer.subprocess, "run", return_value=bad):
                with self.assertRaisesRegex(
                    AssertionError, "^declaration_boundary_process_mismatch$"
                ):
                    consumer.check_declaration_input_boundary(self.case)

    def test_source_short_reads_accept_boundary_and_reject_each_invalid_input(self):
        from qualification import __main__ as cli
        from qualification.tests.test_campaign_bundle_cli import ShortReads

        cases = consumer.declaration_malformed_inputs(self.raw)
        self.assertEqual(
            {key: cases[key] for key in list(cases)[:5]},
            {
                "one_byte_over": self.padded + b" ",
                "trailing_non_whitespace": self.raw + b"PRIVATE",
                "concatenated_json": self.raw * 2,
                "truncated_json": self.raw.rstrip()[:-1],
                "invalid_utf8": b"\xff" + self.raw,
            },
        )
        for name, raw in {"exact_limit": self.padded, **cases}.items():
            with self.subTest(case=name):
                source = ShortReads(raw)
                stdout, stderr = io.StringIO(), io.StringIO()
                with (
                    patch.object(cli.sys, "argv", ["qualification", "--now-ms", "1050"]),
                    patch.object(cli.sys, "stdin", SimpleNamespace(buffer=source)),
                    patch.object(cli.sys, "stdout", stdout),
                    patch.object(cli.sys, "stderr", stderr),
                ):
                    status = cli.main()
                expected = (
                    (0, consumer.canonical(self.report) + "\n", "")
                    if name == "exact_limit"
                    else (2, "", "invalid_qualification_manifest\n")
                )
                self.assertEqual((status, stdout.getvalue(), stderr.getvalue()), expected)
                self.assertEqual(source.tell(), len(raw))
                self.assertFalse(source.closed)

    def test_every_invalid_input_reaches_isolated_binary_cli(self):
        with patch.object(consumer.subprocess, "run", return_value=self.rejected) as run:
            self.assertEqual(consumer.check_declaration_malformed_inputs(self.case), 293)
        self.assertEqual(run.call_count, 293)
        for call, raw in zip(
            run.call_args_list, consumer.declaration_malformed_inputs(self.raw).values()
        ):
            self.assertEqual(
                call.args[0],
                [consumer.sys.executable, "-I", "-m", "qualification", "--now-ms", "1050"],
            )
            self.assertEqual(
                call.kwargs, {"input": raw, "capture_output": True, "check": False, "timeout": 10}
            )

    def test_field_cases_change_only_one_member_and_repair_to_valid_manifest(self):
        original = json.loads(self.raw)
        paths = {
            "root": ((), "version"),
            "rig": (("rig",), "id"),
            "sensor": (("rig", "sensors", 0), "id"),
            "capture": (("capture",), "clock_domain"),
            "record": (("records", 0), "sensor_id"),
        }
        for kind, key in (
            ("calibration", "valid_from_ms"),
            ("clock", "at_ms"),
            ("environment", "lighting"),
        ):
            index = next(i for i, row in enumerate(original["records"]) if row["kind"] == kind)
            paths["data_" + kind] = (("records", index, "data"), key)
        cases = consumer.declaration_malformed_inputs(self.raw)
        self.assertEqual(
            {
                name
                for name in cases
                if not name.startswith(("numeric_", "structure_", "value_", "collection_"))
            }
            - {
                "one_byte_over",
                "trailing_non_whitespace",
                "concatenated_json",
                "truncated_json",
                "invalid_utf8",
            },
            {name + "_" + defect for name in paths for defect in ("duplicate", "unknown")},
        )
        repaired = consumer.canonical(original).encode("ascii")
        expected = copy.deepcopy(
            self.case["expected_report"]["captures"][0]["report"]["declaration"]
        )
        expected["input_sha256"] = hashlib.sha256(repaired).hexdigest()
        for name, (path, key) in paths.items():
            target = original
            for component in path:
                target = target[component]
            for defect in ("duplicate", "unknown"):
                with self.subTest(level=name, defect=defect):
                    duplicates = []

                    def pairs_hook(pairs, duplicates=duplicates):
                        obj = {}
                        for field, value in pairs:
                            if field in obj:
                                duplicates.append((field, obj[field], value, dict(pairs)))
                            obj[field] = value
                        return obj

                    raw = cases[name + "_" + defect]
                    self.assertLessEqual(len(raw), 65536)
                    decoded = json.loads(raw, object_pairs_hook=pairs_hook)
                    if defect == "duplicate":
                        self.assertEqual(duplicates, [(key, target[key], target[key], target)])
                    else:
                        self.assertEqual(duplicates, [])
                        changed = decoded
                        for component in path:
                            changed = changed[component]
                        self.assertEqual(changed.pop("person_identity"), "PRIVATE_MARKER")
                    self.assertEqual(decoded, original)
                    with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
                        consumer.validate(raw, now_ms=1050)
                    fixed = consumer.canonical(decoded).encode("ascii")
                    self.assertEqual(fixed, repaired)
                    self.assertEqual(
                        consumer.canonical(consumer.validate(fixed, now_ms=1050)),
                        consumer.canonical(expected),
                    )

    def test_numeric_cases_change_one_scalar_and_repair_to_pinned_report(self):
        original = json.loads(self.raw)
        clock_index = next(i for i, row in enumerate(original["records"]) if row["kind"] == "clock")
        mutations = {}
        for key, instant in (("start_ms", 1000), ("end_ms", 1050)):
            for name, token in (
                ("boolean", b"true"),
                ("fraction", str(instant + 0.5).encode()),
                ("string", ('"' + str(instant) + '"').encode()),
                ("null", b"null"),
                ("negative", b"-1"),
                ("over_maximum", str(2**53 - 999).encode()),
            ):
                mutations["numeric_capture_" + key + "_" + name] = (("capture",), key, token)
        for name, token in (
            ("nan", b"NaN"),
            ("infinity", b"Infinity"),
            ("overflow", b"1e999"),
            ("boolean", b"true"),
            ("fraction", b"1.0"),
        ):
            mutations["numeric_clock_uncertainty_" + name] = (
                ("records", clock_index, "data"),
                "uncertainty_ms",
                token,
            )
        cases = consumer.declaration_numeric_inputs(self.raw)
        self.assertEqual(set(cases), set(mutations))
        self.assertEqual(len(cases), 17)
        for name, (path, key, token) in mutations.items():
            with self.subTest(case=name):
                doc = copy.deepcopy(original)
                target = doc
                for component in path:
                    target = target[component]
                saved = target[key]
                target[key] = "NUMERIC_PLACEHOLDER"
                template = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
                expected_raw = template.replace(b'"NUMERIC_PLACEHOLDER"', token, 1)
                self.assertEqual(cases[name], expected_raw)
                self.assertLessEqual(len(expected_raw), 65536)
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
                    consumer.validate(cases[name], now_ms=1050)
                # Restoring just this scalar must recover the complete pinned
                # declaration; rejection cannot come from unrelated corruption.
                target[key] = saved
                fixed = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
                self.assertEqual(fixed, self.raw.rstrip())
                expected = copy.deepcopy(
                    self.case["expected_report"]["captures"][0]["report"]["declaration"]
                )
                expected["input_sha256"] = hashlib.sha256(fixed).hexdigest()
                self.assertEqual(
                    consumer.canonical(consumer.validate(fixed, now_ms=1050)),
                    consumer.canonical(expected),
                )

    def test_structure_cases_remove_required_members_or_replace_one_container(self):
        original = json.loads(self.raw)
        # Explicit schema fields keep coverage independent of the case generator
        # and catch accidentally selecting the wrong record's data object.
        objects = {
            "root": ((), "version rig capture records"),
            "rig": (("rig",), "id configuration_sha256 sensors"),
            "sensor": (("rig", "sensors", 0), "id kind device_sha256 mount_sha256"),
            "capture": (("capture",), "clock_domain start_ms end_ms"),
            "record": (
                ("records", 0),
                "sensor_id kind evidence artifact_sha256 rig_sha256 clock_domain data",
            ),
        }
        for kind, fields in (
            ("calibration", "valid_from_ms valid_until_ms"),
            ("clock", "at_ms offset_ms uncertainty_ms"),
            ("environment", "at_ms lighting"),
        ):
            index = next(i for i, row in enumerate(original["records"]) if row["kind"] == kind)
            objects["data_" + kind] = (("records", index, "data"), fields)
        mutations = {}
        for name, (path, fields) in objects.items():
            for key in fields.split():
                mutations["structure_" + name + "_missing_" + key] = (path, key, None)
            mutations["structure_" + name + "_array"] = (path, None, [])
        containers = {name: path for name, (path, _) in objects.items()}
        for name, path in (("sensors", ("rig", "sensors")), ("records", ("records",))):
            containers[name] = path
            mutations["structure_" + name + "_object"] = (path, None, {})
        for name, path in containers.items():
            for defect, value in (
                ("null", None),
                ("string", "PRIVATE"),
                ("boolean", True),
                ("number", 1),
            ):
                mutations["structure_" + name + "_" + defect] = (path, None, value)
        cases = consumer.declaration_structure_inputs(self.raw)
        self.assertEqual(set(cases), set(mutations))
        self.assertEqual(len(cases), 78)
        expected = copy.deepcopy(
            self.case["expected_report"]["captures"][0]["report"]["declaration"]
        )
        for name, (path, missing, value) in mutations.items():
            with self.subTest(case=name):
                decoded = json.loads(cases[name])
                target, saved = decoded, original
                for component in path:
                    saved = saved[component]
                    if missing is not None:
                        target = target[component]
                if missing is not None:
                    self.assertNotIn(missing, target)
                    self.assertEqual(set(target), set(saved) - {missing})
                    target[missing] = saved[missing]
                elif path:
                    for component in path[:-1]:
                        target = target[component]
                    self.assertEqual(
                        consumer.canonical(target[path[-1]]), consumer.canonical(value)
                    )
                    target[path[-1]] = saved
                else:
                    self.assertEqual(consumer.canonical(decoded), consumer.canonical(value))
                    decoded = saved
                self.assertEqual(decoded, original)
                self.assertLessEqual(len(cases[name]), 65536)
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
                    consumer.validate(cases[name], now_ms=1050)
                fixed = json.dumps(decoded, sort_keys=True, separators=(",", ":")).encode()
                self.assertEqual(fixed, self.raw.rstrip())
                expected["input_sha256"] = hashlib.sha256(fixed).hexdigest()
                self.assertEqual(
                    consumer.canonical(consumer.validate(fixed, now_ms=1050)),
                    consumer.canonical(expected),
                )

    def test_value_cases_change_one_field_and_repair_to_pinned_report(self):
        original = json.loads(self.raw)
        environment = next(
            i for i, row in enumerate(original["records"]) if row["kind"] == "environment"
        )
        fields = {
            "version_root": ("version",),
            "enum_sensor_kind": ("rig", "sensors", 0, "kind"),
            "enum_record_kind": ("records", 0, "kind"),
            "enum_evidence": ("records", 0, "evidence"),
            "enum_lighting": ("records", environment, "data", "lighting"),
            "token_rig_id": ("rig", "id"),
            "token_sensor_id": ("rig", "sensors", 0, "id"),
            "token_capture_clock": ("capture", "clock_domain"),
            "token_record_sensor": ("records", 0, "sensor_id"),
            "token_record_clock": ("records", 0, "clock_domain"),
            "digest_configuration": ("rig", "configuration_sha256"),
            "digest_device": ("rig", "sensors", 0, "device_sha256"),
            "digest_mount": ("rig", "sensors", 0, "mount_sha256"),
            "digest_artifact": ("records", 0, "artifact_sha256"),
            "digest_rig_binding": ("records", 0, "rig_sha256"),
        }
        cases = consumer.declaration_value_inputs(self.raw)
        self.assertEqual(len(cases), 164)
        seen = set()
        for field, path in fields.items():
            saved = original
            for key in path:
                saved = saved[key]
            defects = {
                "version": "null boolean number array object future fraction string",
                "enum": "null boolean number array object empty unknown uppercase space",
                "token": "null boolean number array object empty overlong space path non_ascii nul newline",
                "digest": "null boolean number array object empty short long uppercase non_hex non_ascii space",
            }[field.split("_", 1)[0]].split()
            for defect in defects:
                name = "value_" + field + "_" + defect
                seen.add(name)
                with self.subTest(case=name):
                    raw = cases[name]
                    self.assertLessEqual(len(raw), 65536)
                    decoded = json.loads(raw)
                    target = decoded
                    for key in path[:-1]:
                        target = target[key]
                    self.assertNotEqual(
                        consumer.canonical(target[path[-1]]), consumer.canonical(saved)
                    )
                    with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
                        consumer.validate(raw, now_ms=1050)
                    target[path[-1]] = saved
                    self.assertEqual(decoded, original)
                    fixed = json.dumps(decoded, sort_keys=True, separators=(",", ":")).encode()
                    self.assertEqual(fixed, self.raw.rstrip())
                    expected = copy.deepcopy(
                        self.case["expected_report"]["captures"][0]["report"]["declaration"]
                    )
                    expected["input_sha256"] = hashlib.sha256(fixed).hexdigest()
                    self.assertEqual(
                        consumer.canonical(consumer.validate(fixed, now_ms=1050)),
                        consumer.canonical(expected),
                    )
        self.assertEqual(set(cases), seen)

    def test_collection_cases_isolate_constraints_and_repair_to_complete_reports(self):
        original = json.loads(self.raw)
        maximum = copy.deepcopy(original)
        for kind in ("rgb", "radar", "nir"):
            sensor = copy.deepcopy(original["rig"]["sensors"][0])
            sensor.update(id=kind, kind=kind)
            maximum["rig"]["sensors"].append(sensor)
            for template in original["records"][:3]:
                record = copy.deepcopy(template)
                record["sensor_id"] = kind
                maximum["records"].append(record)
        digest = hashlib.sha256(
            json.dumps(maximum["rig"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for record in maximum["records"]:
            record["rig_sha256"] = digest

        # Independent single-container/scalar mutations establish exactly what
        # each case exercises and what must be restored to recover validity.
        mutations = {
            "empty_sensors": (original, ("rig", "sensors"), []),
            "six_sensors": (
                maximum,
                ("rig", "sensors"),
                maximum["rig"]["sensors"] + [dict(maximum["rig"]["sensors"][0], id="sixth")],
            ),
            "sixteen_records": (
                maximum,
                ("records",),
                maximum["records"] + [maximum["records"][0]],
            ),
            "duplicate_sensor_id": (
                original,
                ("rig", "sensors"),
                original["rig"]["sensors"] + [dict(original["rig"]["sensors"][0], kind="rgb")],
            ),
            "duplicate_sensor_kind": (
                original,
                ("rig", "sensors"),
                original["rig"]["sensors"] + [dict(original["rig"]["sensors"][0], id="extra")],
            ),
            "reversed_capture": (original, ("capture", "start_ms"), 1051),
            "reversed_calibration": (original, ("records", 0, "data", "valid_from_ms"), 1101),
        }
        for index, kind in enumerate(("calibration", "clock", "environment")):
            mutations["duplicate_record_" + kind] = (
                original,
                ("records",),
                original["records"] + [original["records"][index]],
            )
            mutations["unknown_sensor_" + kind] = (
                original,
                ("records", index, "sensor_id"),
                "unknown",
            )
        cases = consumer.declaration_collection_inputs(self.raw)
        self.assertEqual(set(cases), {"collection_" + name for name in mutations})
        self.assertEqual(len(cases), 13)
        for name, (base, path, value) in mutations.items():
            with self.subTest(case=name):
                raw = cases["collection_" + name]
                self.assertLessEqual(len(raw), 65536)
                changed = copy.deepcopy(base)
                parent = changed
                for key in path[:-1]:
                    parent = parent[key]
                saved = parent[path[-1]]
                parent[path[-1]] = value
                self.assertEqual(
                    raw, json.dumps(changed, sort_keys=True, separators=(",", ":")).encode()
                )
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
                    consumer.validate(raw, now_ms=1050)
                parent[path[-1]] = saved
                fixed = json.dumps(changed, sort_keys=True, separators=(",", ":")).encode()
                expected = copy.deepcopy(
                    self.case["expected_report"]["captures"][0]["report"]["declaration"]
                )
                expected["input_sha256"] = hashlib.sha256(fixed).hexdigest()
                if base is maximum:
                    expected.update(sensor_count=5, record_count=15)
                    expected["evidence_counts"]["synthetic"] = 15
                self.assertEqual(
                    consumer.canonical(consumer.validate(fixed, now_ms=1050)),
                    consumer.canonical(expected),
                )
        self.assertEqual(json.loads(self.raw), original)

    def test_collection_counts_reject_before_visiting_entries(self):
        from qualification import evidence

        cases = consumer.declaration_collection_inputs(self.raw)
        keys = evidence._keys
        for name, entry_fields in (
            ("empty_sensors", "clock_domain start_ms end_ms"),
            ("six_sensors", "id kind device_sha256 mount_sha256"),
            (
                "sixteen_records",
                "sensor_id kind evidence artifact_sha256 rig_sha256 clock_domain data",
            ),
        ):

            def guard(value, names, entry_fields=entry_fields):
                self.assertNotEqual(names, entry_fields, "entries visited before count admission")
                return keys(value, names)

            with self.subTest(case=name), patch.object(evidence, "_keys", side_effect=guard):
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
                    consumer.validate(cases["collection_" + name], now_ms=1050)

    def test_each_invalid_input_checks_status_empty_stdout_and_fixed_diagnostic(self):
        for index, name in enumerate(consumer.declaration_malformed_inputs(self.raw)):
            for status, stdout, stderr in (
                (0, b"", self.fixed),
                (1, b"", self.fixed),
                (2, self.raw, self.fixed),
                (2, b"PRIVATE", self.fixed),
                (2, b"", b""),
                (2, b"", self.fixed + b"PRIVATE"),
                (2, b"", b"Traceback"),
            ):
                with self.subTest(case=name, status=status, stdout=stdout, stderr=stderr):
                    bad = SimpleNamespace(returncode=status, stdout=stdout, stderr=stderr)
                    with patch.object(
                        consumer.subprocess, "run", side_effect=[self.rejected] * index + [bad]
                    ):
                        with self.assertRaises(AssertionError) as error:
                            consumer.check_declaration_malformed_inputs(self.case)
                    self.assertEqual(
                        str(error.exception), "declaration_input_process_mismatch:" + name
                    )


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


class BundleExactLimitConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = consumer.bundle_corpus(BUNDLE_CORPUS)
        cls.case = next(case for case in cls.data["cases"] if case["id"] == "complete")
        cls.args = consumer.bundle_exact_limit_arguments(
            consumer.bundle_arguments(cls.data, cls.case)
        )
        cls.report = consumer.evaluate_bundle(*cls.args)
        cls.output = (consumer.canonical(cls.report) + os.linesep).encode("ascii")

    def test_exact_bounds_match_independent_source_encoder_and_binary_process(self):
        from qualification import campaign_bundle_cli
        from qualification.tests.test_campaign_bundle_cli import frame

        plan, rows, domain, procedure = self.args
        self.assertEqual(len(plan), 65536)
        self.assertEqual(domain, b"\xff" * 1048576)
        self.assertEqual(procedure, b"\0" * 1048576)
        self.assertEqual(len(rows), 64)
        for row in rows:
            self.assertEqual(row["case_id"], "a" * 64)
            self.assertEqual(len(row["manifest"]), 65536)
        raw = frame(*self.args)
        self.assertEqual(raw, consumer.bundle_frame(self.args))
        self.assertEqual(campaign_bundle_cli._report(io.BytesIO(raw)), self.report)
        original = copy.deepcopy(self.data)
        good = SimpleNamespace(returncode=1, stdout=self.output, stderr=b"")
        with patch.object(consumer.subprocess, "run", return_value=good) as run:
            self.assertEqual(consumer.check_bundle_exact_limits(self.data, self.case), 1)
        self.assertEqual(self.data, original)
        self.assertEqual(
            run.call_args.args[0],
            [consumer.sys.executable, "-I", "-m", "qualification.campaign_bundle_cli"],
        )
        self.assertEqual(
            run.call_args.kwargs,
            {"input": raw, "capture_output": True, "check": False, "timeout": 10},
        )

    def test_every_report_leaf_is_checked_including_types_and_false_claims(self):
        def leaves(value, path=()):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield from leaves(child, (*path, key))
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    yield from leaves(child, (*path, index))
            else:
                yield path, value

        for path, original in leaves(self.report):
            for value in (None, 0 if type(original) is bool else True):
                with self.subTest(path=path, value=value):
                    report = copy.deepcopy(self.report)
                    target = report
                    for key in path[:-1]:
                        target = target[key]
                    target[path[-1]] = value
                    with patch.object(consumer, "evaluate_bundle", return_value=report):
                        with self.assertRaisesRegex(
                            AssertionError, "^exact_limit_bundle_report_mismatch$"
                        ):
                            consumer.check_bundle_exact_limits(self.data, self.case)

    def test_process_cannot_reject_exact_limit_or_hide_negative_result(self):
        for status, stdout, stderr in (
            (0, self.output, b""),
            (2, b"", b"invalid_campaign_bundle" + os.linesep.encode("ascii")),
            (1, b"{}" + os.linesep.encode("ascii"), b""),
            (1, self.output + b"PRIVATE", b""),
            (1, self.output, b"PRIVATE"),
        ):
            with self.subTest(status=status, stderr=stderr):
                result = SimpleNamespace(returncode=status, stdout=stdout, stderr=stderr)
                with patch.object(consumer.subprocess, "run", return_value=result):
                    with self.assertRaisesRegex(
                        AssertionError, "^exact_limit_bundle_process_mismatch$"
                    ):
                        consumer.check_bundle_exact_limits(self.data, self.case)


class BundleScalarConsumerTests(unittest.TestCase):
    def setUp(self):
        self.data = consumer.bundle_corpus(BUNDLE_CORPUS)
        self.case = next(case for case in self.data["cases"] if case["id"] == "complete")
        self.args = []
        self.reports = []
        self.results = []
        for instant in (0, 2**53 - 1000):
            args = consumer.bundle_arguments(self.data, self.case)
            args[1][0]["now_ms"] = instant
            report = consumer.evaluate_bundle(*args)
            self.args.append(args)
            self.reports.append(report)
            self.results.append(
                SimpleNamespace(
                    returncode=1,
                    stdout=(consumer.canonical(report) + os.linesep).encode("ascii"),
                    stderr=b"",
                )
            )

    def test_boundaries_preserve_uint64_frames_and_negative_evidence(self):
        from qualification import campaign_bundle_cli
        from qualification.tests.test_campaign_bundle_cli import frame

        with patch.object(consumer.subprocess, "run", side_effect=self.results) as run:
            self.assertEqual(consumer.check_bundle_scalar_boundaries(self.data, self.case), 2)
        for args, report, call in zip(self.args, self.reports, run.call_args_list):
            raw = frame(*args)
            self.assertEqual(
                call.args[0],
                [consumer.sys.executable, "-I", "-m", "qualification.campaign_bundle_cli"],
            )
            self.assertEqual(
                call.kwargs,
                {
                    "input": raw,
                    "capture_output": True,
                    "check": False,
                    "timeout": 10,
                },
            )
            self.assertEqual(campaign_bundle_cli._report(io.BytesIO(raw)), report)
            with patch.object(campaign_bundle_cli, "evaluate") as evaluate:
                campaign_bundle_cli._report(io.BytesIO(raw))
                evaluate.assert_called_once_with(*args)
                self.assertIs(type(evaluate.call_args.args[1][0]["now_ms"]), int)

    def test_library_cannot_hide_time_findings_or_change_typed_report(self):
        mutations = [
            (("coverage", "findings"), []),
            (("coverage", "captures_sha256"), "0" * 64),
            (("coverage", "capture_counts", "eligible"), False),
            (("coverage", "cases", 0, "eligible"), 0.0),
            (("coverage", "declaration_coverage_complete"), True),
            (("software_checks_passed",), True),
        ]
        for prefix in ((), ("coverage",), ("references",)):
            for key in (
                "physical_qualification_passed",
                "artifact_authenticity_verified",
                "domain_verified",
                "procedure_verified",
            ):
                mutations.append(((*prefix, key), True))
        for index in range(2):
            for path, value in mutations:
                with self.subTest(index=index, path=path):
                    reports = copy.deepcopy(self.reports)
                    target = reports[index]
                    for key in path[:-1]:
                        target = target[key]
                    target[path[-1]] = value
                    with (
                        patch.object(consumer, "evaluate_bundle", side_effect=reports),
                        patch.object(consumer.subprocess, "run", side_effect=self.results),
                        self.assertRaisesRegex(
                            AssertionError, "^scalar_boundary_bundle_report_mismatch$"
                        ),
                    ):
                        consumer.check_bundle_scalar_boundaries(self.data, self.case)

    def test_process_outcome_is_checked_at_both_boundaries(self):
        for index in range(2):
            for status, stdout, stderr in (
                (0, self.results[index].stdout, b""),
                (2, b"", b"invalid_campaign_bundle" + os.linesep.encode("ascii")),
                (1, self.results[1 - index].stdout, b""),
                (1, self.results[index].stdout, b"PRIVATE"),
            ):
                with self.subTest(index=index, status=status, stderr=stderr):
                    results = list(self.results)
                    results[index] = SimpleNamespace(
                        returncode=status, stdout=stdout, stderr=stderr
                    )
                    with patch.object(consumer.subprocess, "run", side_effect=results):
                        with self.assertRaisesRegex(
                            AssertionError, "^scalar_boundary_bundle_process_mismatch$"
                        ):
                            consumer.check_bundle_scalar_boundaries(self.data, self.case)


class UnexpectedArgumentConsumerTests(unittest.TestCase):
    def cases(self):
        from qualification import assessment_cli, campaign_bundle_cli
        from qualification.tests.test_assessment_cli import frame
        from qualification.tests.test_campaign_bundle_cli import frame as bundle_frame

        complete = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        data = consumer.bundle_corpus(BUNDLE_CORPUS)
        bundle = next(case for case in data["cases"] if case["id"] == "complete")
        bundle_args = consumer.bundle_arguments(data, bundle)
        return (
            (
                assessment_cli,
                frame(consumer.arguments(complete)),
                complete["expected_report"],
                "invalid_qualification_assessment",
            ),
            (
                campaign_bundle_cli,
                bundle_frame(*bundle_args),
                consumer.evaluate_bundle(*bundle_args),
                "invalid_campaign_bundle",
            ),
        )

    def test_complete_inputs_and_exact_isolated_argument_vectors(self):
        expected_args = [
            ["--PRIVATE"],
            ["--help"],
            ["-h"],
            ["PRIVATE"],
            [""],
            ["--"],
            ["--input", "PRIVATE path with spaces"],
            ["--", "PRIVATE"],
        ]
        self.assertEqual(list(consumer.unexpected_arguments().values()), expected_args)
        for module, raw, report, diagnostic in self.cases():
            # Independently encoded complete inputs really reach successful evaluation.
            self.assertEqual(
                consumer.canonical(module._report(io.BytesIO(raw))), consumer.canonical(report)
            )
            self.assertIs(report["software_checks_passed"], True)
            result = SimpleNamespace(
                returncode=2, stdout=b"", stderr=(diagnostic + os.linesep).encode("ascii")
            )
            with patch.object(consumer.subprocess, "run", return_value=result) as run:
                self.assertEqual(
                    consumer.check_unexpected_arguments(module.__name__, raw, diagnostic), 8
                )
            self.assertEqual(run.call_count, 8)
            for call, args in zip(run.call_args_list, expected_args):
                self.assertEqual(
                    call.args[0], [consumer.sys.executable, "-I", "-m", module.__name__, *args]
                )
                self.assertEqual(
                    call.kwargs,
                    {"input": raw, "capture_output": True, "check": False, "timeout": 10},
                )

    def test_each_argument_case_checks_status_stdout_and_fixed_diagnostic(self):
        for module, raw, _report, diagnostic in self.cases():
            fixed = (diagnostic + os.linesep).encode("ascii")
            good = SimpleNamespace(returncode=2, stdout=b"", stderr=fixed)
            for index, name in enumerate(consumer.unexpected_arguments()):
                for status, stdout, stderr in (
                    (0, b"", fixed),
                    (1, b"", fixed),
                    (2, raw, fixed),
                    (2, b"PRIVATE", fixed),
                    (2, b"", b""),
                    (2, b"", fixed + b"PRIVATE"),
                    (2, b"", raw),
                    (2, b"", b"usage: --help"),
                ):
                    with self.subTest(module=module.__name__, case=name, status=status):
                        bad = SimpleNamespace(returncode=status, stdout=stdout, stderr=stderr)
                        with patch.object(
                            consumer.subprocess, "run", side_effect=[good] * index + [bad]
                        ):
                            with self.assertRaises(AssertionError) as error:
                                consumer.check_unexpected_arguments(
                                    module.__name__, raw, diagnostic
                                )
                        self.assertEqual(
                            str(error.exception),
                            "argument_process_mismatch:" + module.__name__ + ":" + name,
                        )


class ClosedPipeConsumerTests(unittest.TestCase):
    def cases(self):
        from qualification import assessment_cli, campaign_bundle_cli
        from qualification.tests.test_assessment_cli import frame
        from qualification.tests.test_campaign_bundle_cli import frame as bundle_frame

        assessments = consumer.corpus(CORPUS)
        data = consumer.bundle_corpus(BUNDLE_CORPUS)
        declarations, declaration_args = consumer.declaration_closed_pipe_inputs(assessments)
        complete = next(case for case in assessments if case["id"] == "complete")
        manifest = bytes.fromhex(complete["captures"][0]["manifest_hex"])
        return (
            (
                consumer.qualification,
                declarations,
                {"complete": manifest, "stale": manifest, "malformed": b"PRIVATE malformed"},
                "invalid_qualification_manifest",
                declaration_args,
            ),
            (
                assessment_cli,
                consumer.closed_pipe_frames(
                    assessments, lambda case: consumer.frame(consumer.arguments(case))
                ),
                consumer.closed_pipe_frames(
                    assessments, lambda case: frame(consumer.arguments(case))
                ),
                "invalid_qualification_assessment",
                None,
            ),
            (
                campaign_bundle_cli,
                consumer.closed_pipe_frames(
                    data["cases"],
                    lambda case: consumer.bundle_frame(consumer.bundle_arguments(data, case)),
                ),
                consumer.closed_pipe_frames(
                    data["cases"], lambda case: bundle_frame(*consumer.bundle_arguments(data, case))
                ),
                "invalid_campaign_bundle",
                None,
            ),
        )

    def test_inputs_reach_distinct_outcomes_and_pipes_have_no_readers(self):
        for module, cases, independent, diagnostic, arguments in self.cases():
            self.assertEqual(cases, independent)
            self.assertEqual(list(cases), ["complete", "stale", "malformed"])
            if arguments is not None:
                self.assertEqual(
                    arguments,
                    {
                        "complete": ["--now-ms", "1050"],
                        "stale": ["--now-ms", "1151"],
                        "malformed": ["--now-ms", "1050"],
                    },
                )
            for name, expected in (("complete", True), ("stale", False)):
                if arguments is None:
                    report = module._report(io.BytesIO(cases[name]))
                    self.assertIs(report["software_checks_passed"], expected)
                else:
                    report = consumer.validate(cases[name], now_ms=int(arguments[name][1]))
                    self.assertIs(report["declaration_checks_passed"], expected)
            with self.assertRaises(ValueError):
                if arguments is None:
                    module._report(io.BytesIO(cases["malformed"]))
                else:
                    consumer.validate(cases["malformed"], now_ms=1050)

            streams = []

            def run(
                command,
                *,
                input,
                stdout,
                stderr,
                check,
                timeout,
                streams=streams,
                module=module,
                cases=cases,
                diagnostic=diagnostic,
                arguments=arguments,
            ):
                index = len(streams)
                name = list(cases)[index // 2]
                args = [] if arguments is None else arguments[name]
                self.assertEqual(
                    command, [consumer.sys.executable, "-I", "-m", module.__name__, *args]
                )
                self.assertEqual(input, list(cases.values())[index // 2])
                self.assertIs(check, False)
                self.assertEqual(timeout, 10)
                opened = [stdout]
                if index % 2:
                    opened.append(stderr)
                else:
                    self.assertEqual(stderr, consumer.subprocess.PIPE)
                for stream in opened:
                    self.assertEqual(stream.mode, "wb")
                    with self.assertRaises(OSError) as error:
                        os.write(stream.fileno(), b"probe")
                    # The Windows CRT reports EINVAL for this reader-free pipe;
                    # POSIX reports EPIPE. Do not accept unrelated I/O failures.
                    self.assertEqual(
                        error.exception.errno, errno.EINVAL if os.name == "nt" else errno.EPIPE
                    )
                streams.append(opened)
                return SimpleNamespace(
                    returncode=2,
                    stdout=None,
                    stderr=None if index % 2 else (diagnostic + os.linesep).encode("ascii"),
                )

            with patch.object(consumer.subprocess, "run", side_effect=run):
                self.assertEqual(
                    consumer.check_closed_pipes(
                        module.__name__, cases, diagnostic, case_arguments=arguments
                    ),
                    6,
                )
            self.assertEqual(len(streams), 6)
            self.assertTrue(all(stream.closed for opened in streams for stream in opened))

    def test_every_pipe_case_checks_status_and_observable_diagnostic(self):
        for module, cases, _independent, diagnostic, arguments in self.cases():
            fixed = (diagnostic + os.linesep).encode("ascii")
            preceding = []
            for name in cases:
                for close_errors in (False, True):
                    errors = None if close_errors else fixed
                    bad_results = [(status, None, errors) for status in (0, 1, 120, -13)]
                    bad_results += [(2, b"PRIVATE", errors)]
                    bad_results += [
                        (2, None, bad) for bad in (b"", fixed + b"PRIVATE", b"Traceback")
                    ]
                    if not close_errors:
                        bad_results.append((2, None, None))
                    for status, stdout, stderr in bad_results:
                        with self.subTest(module=module.__name__, case=name, closed=close_errors):
                            bad = SimpleNamespace(returncode=status, stdout=stdout, stderr=stderr)
                            with patch.object(
                                consumer.subprocess, "run", side_effect=[*preceding, bad]
                            ):
                                with self.assertRaises(AssertionError) as error:
                                    consumer.check_closed_pipes(
                                        module.__name__, cases, diagnostic, case_arguments=arguments
                                    )
                            mode = "both" if close_errors else "stdout"
                            self.assertEqual(
                                str(error.exception),
                                "closed_pipe_process_mismatch:"
                                + module.__name__
                                + ":"
                                + name
                                + ":"
                                + mode,
                            )
                    preceding.append(SimpleNamespace(returncode=2, stdout=None, stderr=errors))

    def test_subprocess_failure_closes_descriptors_and_cannot_report_success(self):
        for fail_at in (0, 1):
            streams = []

            def run(*args, streams=streams, fail_at=fail_at, **kwargs):
                streams.append(kwargs["stdout"])
                if kwargs["stderr"] != consumer.subprocess.PIPE:
                    streams.append(kwargs["stderr"])
                if len(streams) > fail_at:
                    raise consumer.subprocess.TimeoutExpired(args[0], kwargs["timeout"])
                return SimpleNamespace(
                    returncode=2, stdout=None, stderr=b"fixed" + os.linesep.encode()
                )

            with patch.object(consumer.subprocess, "run", side_effect=run):
                with self.assertRaises(consumer.subprocess.TimeoutExpired):
                    consumer.check_closed_pipes("test.module", {"complete": b"data"}, "fixed")
            self.assertEqual(len(streams), 1 if fail_at == 0 else 3)
            self.assertTrue(all(stream.closed for stream in streams))


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
                25,
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

    def test_bundle_complete_oversized_frames_have_single_field_repairs(self):
        from qualification import campaign_bundle_cli
        from qualification.tests.test_campaign_bundle_cli import NoReadPastHeader, frame

        data = consumer.bundle_corpus(BUNDLE_CORPUS)
        case = next(case for case in data["cases"] if case["id"] == "complete")
        original = consumer.bundle_arguments(data, case)
        cases = consumer.bundle_malformed_frames(original)
        limits = {
            "plan": ((0,), 65536),
            "domain": ((2,), 1048576),
            "procedure": ((3,), 1048576),
            "manifest": ((1, 0, "manifest"), 65536),
            "capture_count": ((1,), 64),
            "case_id": ((1, 0, "case_id"), 64),
        }
        for name, (path, limit) in limits.items():
            with self.subTest(case=name):
                args = list(copy.deepcopy(original))
                target = args
                for key in path[:-1]:
                    target = target[key]
                key = path[-1]
                if name == "capture_count":
                    value = [dict(original[1][0]) for _ in range(limit + 1)]
                elif name == "case_id":
                    value = "a" * (limit + 1)
                else:
                    value = target[key].ljust(limit + 1, b" ")
                target[key] = value
                raw = cases["oversized_" + name + "_frame"]
                self.assertEqual(raw, frame(*args))
                header = cases["oversized_" + name]
                self.assertTrue(raw.startswith(header))
                with patch.object(campaign_bundle_cli, "evaluate") as evaluate:
                    for stream in (io.BytesIO(raw), NoReadPastHeader(header)):
                        with self.assertRaises(ValueError):
                            campaign_bundle_cli._report(stream)
                    evaluate.assert_not_called()
                target[key] = value[:-1]
                sentinel = object()
                with patch.object(
                    campaign_bundle_cli, "evaluate", return_value=sentinel
                ) as evaluate:
                    self.assertIs(campaign_bundle_cli._report(io.BytesIO(frame(*args))), sentinel)
                    evaluate.assert_called_once_with(*args)
                report = campaign_bundle_cli._report(io.BytesIO(frame(*args)))
                self.assertIs(report["physical_qualification_passed"], False)
                self.assertEqual(report, consumer.evaluate_bundle(*args))

    def test_bundle_scalar_frames_reject_before_later_reads_and_have_repairs(self):
        from qualification import campaign_bundle_cli
        from qualification.tests.test_campaign_bundle_cli import (
            MAGIC,
            NoReadPastHeader,
            blob,
            frame,
        )

        data = consumer.bundle_corpus(BUNDLE_CORPUS)
        case = next(case for case in data["cases"] if case["id"] == "complete")
        args = consumer.bundle_arguments(data, case)
        plan, rows, domain, procedure = args
        row = rows[0]
        prefix = MAGIC + blob(plan) + blob(domain) + blob(procedure) + struct.pack(">I", 1)
        cases = consumer.bundle_malformed_frames(args)
        names = set()
        for name, token in (
            ("empty", b""),
            ("space", b"PRIVATE name"),
            ("path", b"a/b"),
            ("non_ascii", b"\xff"),
        ):
            names.add("case_id_" + name + "_frame")
            header = prefix + blob(token)
            suffix = struct.pack(">Q", row["now_ms"]) + blob(row["manifest"])
            raw = cases["case_id_" + name + "_frame"]
            self.assertEqual(raw, header + suffix)
            with self.subTest(case=name), patch.object(campaign_bundle_cli, "evaluate") as evaluate:
                for stream in (io.BytesIO(raw), NoReadPastHeader(header)):
                    with self.assertRaises(ValueError):
                        campaign_bundle_cli._report(stream)
                evaluate.assert_not_called()
                repaired = prefix + blob(row["case_id"].encode("ascii")) + suffix
                self.assertEqual(repaired, frame(*args))
                campaign_bundle_cli._report(io.BytesIO(repaired))
                evaluate.assert_called_once_with(*args)
        for name, instant in (("above_maximum", 2**53 - 999), ("uint64_maximum", 2**64 - 1)):
            names.add("instant_" + name + "_frame")
            args[1][0]["now_ms"] = instant
            raw = cases["instant_" + name + "_frame"]
            self.assertEqual(raw, frame(*args))
            header = raw[: len(prefix) + 4 + len(row["case_id"]) + 8]
            with self.subTest(case=name), patch.object(campaign_bundle_cli, "evaluate") as evaluate:
                for stream in (io.BytesIO(raw), NoReadPastHeader(header)):
                    with self.assertRaises(ValueError):
                        campaign_bundle_cli._report(stream)
                evaluate.assert_not_called()
                args[1][0]["now_ms"] = 2**53 - 1000
                repaired = header[:-8] + struct.pack(">Q", 2**53 - 1000) + raw[len(header) :]
                self.assertEqual(repaired, frame(*args))
                campaign_bundle_cli._report(io.BytesIO(repaired))
                evaluate.assert_called_once_with(*args)
        self.assertEqual(
            names, {name for name in cases if name.startswith(("instant_", "case_id_"))}
        )

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
