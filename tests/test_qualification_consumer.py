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
        for name, (raw, report) in self.cases.items():
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
                    ("evidence_counts", dict(report["evidence_counts"], **{kind: incorrect}))
                    for kind, count in report["evidence_counts"].items()
                    for incorrect in (float(count), count + 1)
                ),
            ):
                changed = copy.deepcopy(report)
                changed[key] = value
                for mode in ("report", "process"):
                    with self.subTest(case=name, field=key, mode=mode):
                        result = self.result(report)
                        if mode == "process":
                            result.stdout = self.encode(changed) + os.linesep.encode()
                        with (
                            patch.object(
                                consumer, self.generate.__name__, return_value={name: (raw, report)}
                            ),
                            patch.object(
                                consumer,
                                "validate",
                                return_value=changed if mode == "report" else report,
                            ) as validate,
                            patch.object(consumer.subprocess, "run", return_value=result) as run,
                        ):
                            with self.assertRaisesRegex(
                                AssertionError,
                                "^" + self.diagnostic + mode + "_mismatch:" + name + "$",
                            ):
                                self.check(self.case)
                        validate.assert_called_once_with(raw, now_ms=1050)
                        if mode == "report":
                            run.assert_not_called()
                        else:
                            self.assert_process_call(run, raw)

    def assert_process_call(self, run, raw):
        run.assert_called_once_with(
            [consumer.sys.executable, "-I", "-m", "qualification", "--now-ms", "1050"],
            input=raw,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def test_every_boundary_checks_exit_status_stdout_and_stderr(self):
        for name, (raw, report) in self.cases.items():
            good = self.result(report)
            for key, value in (
                ("returncode", 1 - good.returncode),
                ("returncode", 2),
                ("stdout", b""),
                ("stdout", good.stdout.rstrip(b"\r\n")),
                ("stdout", good.stdout + b"PRIVATE"),
                ("stderr", b"PRIVATE"),
            ):
                with self.subTest(case=name, field=key):
                    result = copy.copy(good)
                    setattr(result, key, value)
                    with (
                        patch.object(
                            consumer, self.generate.__name__, return_value={name: (raw, report)}
                        ),
                        patch.object(consumer, "validate", wraps=consumer.validate) as validate,
                        patch.object(consumer.subprocess, "run", return_value=result) as run,
                    ):
                        with self.assertRaisesRegex(
                            AssertionError, "^" + self.diagnostic + "process_mismatch:" + name + "$"
                        ):
                            self.check(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    self.assert_process_call(run, raw)


def escaped_key_documents(case):
    """Independent path-based encoder; preserve all untouched object members."""
    doc = json.loads(bytes.fromhex(case["captures"][0]["manifest_hex"]))
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
        index = next(i for i, row in enumerate(doc["records"]) if row["kind"] == kind)
        paths["data_" + kind] = (("records", index, "data"), key)
    controls, duplicates = {}, {}
    for name, (target_path, target_key) in paths.items():
        literal = json.dumps(target_key)
        # Encode from ASCII bytes independently of the consumer's ord-based code.
        escapes = ["\\u00" + bytes([byte]).hex() for byte in target_key.encode("ascii")]
        partial = '"' + escapes[0] + target_key[1:] + '"'
        full = '"' + "".join(escapes) + '"'

        def encode(value, path, token, extra, target_path=target_path, target_key=target_key):
            if isinstance(value, dict):
                members = []
                if path == target_path and extra is not None:
                    members.append(extra + ":" + json.dumps(value[target_key]))
                for key in sorted(value):
                    member_key = (
                        token if path == target_path and key == target_key else json.dumps(key)
                    )
                    members.append(
                        member_key + ":" + encode(value[key], (*path, key), token, extra)
                    )
                return "{" + ",".join(members) + "}"
            if isinstance(value, list):
                return (
                    "["
                    + ",".join(encode(row, (*path, i), token, extra) for i, row in enumerate(value))
                    + "]"
                )
            return json.dumps(value)

        for form, token, extra in (
            ("partial", partial, None),
            ("full", full, None),
            ("literal_partial", partial, literal),
            ("partial_literal", literal, partial),
            ("partial_full", full, partial),
        ):
            raw = encode(doc, (), token, extra).encode("ascii")
            if extra is None:
                report = {
                    "version": 1,
                    "input_sha256": hashlib.sha256(raw).hexdigest(),
                    "declaration_checks_passed": True,
                    "sensor_count": 2,
                    "record_count": 6,
                    "evidence_counts": {"synthetic": 6, "recorded": 0, "external_unverified": 0},
                    "findings": [],
                    "artifacts_verified": False,
                    "physical_qualification_passed": False,
                    "physical_status": "blocked_external_evidence_and_review",
                }
                controls[name + "_" + form] = raw, report
            else:
                duplicates[name + "_" + form] = raw, target_path, target_key
    return controls, duplicates


class DeclarationEscapedKeyControlTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_escaped_key_controls)
    check = staticmethod(consumer.check_declaration_escaped_key_controls)
    diagnostic = "declaration_escaped_key_"
    count = 16

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        self.cases, _ = escaped_key_documents(self.case)

    def test_encodings_preserve_semantics_but_commit_exact_bytes(self):
        raw = bytes.fromhex(self.case["captures"][0]["manifest_hex"])
        canonical_digest = hashlib.sha256(self.encode(json.loads(raw))).hexdigest()
        for name, (encoded, report) in self.cases.items():
            with self.subTest(case=name):
                self.assertEqual(json.loads(encoded), json.loads(raw))
                self.assertNotEqual(report["input_sha256"], hashlib.sha256(raw).hexdigest())
                self.assertNotEqual(report["input_sha256"], canonical_digest)
                self.assertIn(b"\\u00", encoded)
                self.assertEqual(
                    self.encode(consumer.validate(encoded, now_ms=1050)), self.encode(report)
                )

    def test_valid_escapes_cannot_clear_existing_stale_findings(self):
        case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "stale")
        cases = self.generate(case)
        for raw, report in cases.values():
            self.assertEqual(report["findings"], ["capture_stale"])
            self.assertFalse(report["declaration_checks_passed"])
            self.assertEqual(self.encode(consumer.validate(raw, now_ms=1151)), self.encode(report))
        with patch.object(
            consumer.subprocess, "run", side_effect=[self.result(r) for _, r in cases.values()]
        ):
            self.assertEqual(self.check(case), 16)


class DeclarationEscapedValueControlTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_escaped_value_controls)
    check = staticmethod(consumer.check_declaration_escaped_value_controls)
    diagnostic = "declaration_escaped_value_"
    count = 16

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        doc = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        groups = {
            "rig_id": [(doc["rig"], "id")],
            "rig_hashes": [(doc["rig"], "configuration_sha256")]
            + [
                (sensor, key)
                for sensor in doc["rig"]["sensors"]
                for key in ("device_sha256", "mount_sha256")
            ],
        }
        for i, sensor in enumerate(doc["rig"]["sensors"]):
            groups["sensor_" + str(i)] = [(sensor, "id")] + [
                (row, "sensor_id") for row in doc["records"] if row["sensor_id"] == sensor["id"]
            ]
        groups["capture_clock"] = [(doc["capture"], "clock_domain")]
        groups["record_clocks"] = [(row, "clock_domain") for row in doc["records"]]
        groups["rig_commitments"] = [(row, "rig_sha256") for row in doc["records"]]
        groups["combined"] = [member for members in groups.values() for member in members]
        self.cases = {}
        for name, members in groups.items():
            for form in ("partial", "full"):
                replacements = {}
                originals = []
                for index, (obj, key) in enumerate(members):
                    value = obj[key]
                    escaped = [b"\\u00" + bytes([c]).hex().encode() for c in value.encode("ascii")]
                    token = (
                        b'"'
                        + (
                            escaped[0] + value[1:].encode()
                            if form == "partial"
                            else b"".join(escaped)
                        )
                        + b'"'
                    )
                    marker = "ESCAPED_VALUE_" + str(index)
                    originals.append((obj, key, value))
                    obj[key] = marker
                    replacements[self.encode(marker)] = token
                # Placeholders let the standard JSON encoder preserve every
                # unrelated member; no path walker or production oracle is used.
                raw = self.encode(doc)
                for marker, token in replacements.items():
                    raw = raw.replace(marker, token)
                for obj, key, value in originals:
                    obj[key] = value
                report = {
                    "version": 1,
                    "input_sha256": hashlib.sha256(raw).hexdigest(),
                    "declaration_checks_passed": True,
                    "sensor_count": 2,
                    "record_count": 6,
                    "evidence_counts": {"synthetic": 6, "recorded": 0, "external_unverified": 0},
                    "findings": [],
                    "artifacts_verified": False,
                    "physical_qualification_passed": False,
                    "physical_status": "blocked_external_evidence_and_review",
                }
                self.cases[name + "_" + form] = raw, report

    def test_escapes_preserve_decoded_references_and_canonical_rig_bindings(self):
        original = bytes.fromhex(self.case["captures"][0]["manifest_hex"])
        doc = json.loads(original)
        rig_digest = hashlib.sha256(self.encode(doc["rig"])).hexdigest()
        commitments = set()
        for name, (raw, report) in self.cases.items():
            with self.subTest(case=name):
                decoded = json.loads(raw)
                self.assertEqual(decoded, doc)
                self.assertEqual({r["rig_sha256"] for r in decoded["records"]}, {rig_digest})
                self.assertIn(b"\\u00", raw)
                self.assertNotEqual(report["input_sha256"], hashlib.sha256(original).hexdigest())
                self.assertNotEqual(
                    report["input_sha256"], hashlib.sha256(self.encode(doc)).hexdigest()
                )
                commitments.add(report["input_sha256"])
                self.assertEqual(
                    self.encode(consumer.validate(raw, now_ms=1050)), self.encode(report)
                )
        self.assertEqual(len(commitments), self.count)

    def test_escapes_cannot_clear_stale_or_wrong_rig_findings(self):
        for case_id in ("complete", "stale"):
            case = next(c for c in consumer.corpus(CORPUS) if c["id"] == case_id)
            changed = copy.deepcopy(case)
            doc = json.loads(bytes.fromhex(changed["captures"][0]["manifest_hex"]))
            doc["records"][0]["rig_sha256"] = "0" * 64
            changed["captures"][0]["manifest_hex"] = self.encode(doc).hex()
            report = changed["expected_report"]["captures"][0]["report"]["declaration"]
            report["declaration_checks_passed"] = False
            report["findings"] = sorted([*report["findings"], "rig_binding_mismatch"])
            for source in (case, changed):
                cases = self.generate(source)
                instant = source["captures"][0]["now_ms"]
                for name, (raw, expected) in cases.items():
                    with self.subTest(case=case_id, encoding=name, findings=expected["findings"]):
                        self.assertEqual(
                            self.encode(consumer.validate(raw, now_ms=instant)),
                            self.encode(expected),
                        )
                with patch.object(
                    consumer.subprocess,
                    "run",
                    side_effect=[self.result(r) for _, r in cases.values()],
                ):
                    self.assertEqual(self.check(source), self.count)


class DeclarationEscapedKeyDuplicateTests(unittest.TestCase):
    assert_process_call = DeclarationCollectionBoundaryTests.assert_process_call

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        self.controls, self.details = escaped_key_documents(self.case)
        self.cases = {name: raw for name, (raw, _, _) in self.details.items()}
        self.good = SimpleNamespace(
            returncode=2,
            stdout=b"",
            stderr=("invalid_qualification_manifest" + os.linesep).encode("ascii"),
        )

    def test_independent_documents_decode_one_duplicate_at_the_intended_path(self):
        original = copy.deepcopy(self.case)
        self.assertEqual(consumer.declaration_escaped_key_duplicates(self.case), self.cases)
        for name, (raw, path, key) in self.details.items():
            with self.subTest(case=name):
                found = []

                def pairs_hook(pairs, found=found):
                    result = {}
                    for field, value in pairs:
                        if field in result:
                            found.append((field, result[field], value, dict(pairs)))
                        result[field] = value
                    return result

                doc = json.loads(raw, object_pairs_hook=pairs_hook)
                target = doc
                for part in path:
                    target = target[part]
                self.assertEqual(found, [(key, target[key], target[key], target)])
                self.assertEqual(
                    doc, json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
                )
                self.assertLessEqual(len(raw), 65536)
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
                    consumer.validate(raw, now_ms=1050)
                # Removing the prepended duplicate leaves a valid singly encoded key.
                level, form = name.rsplit("_", 2)[0], name.rsplit("_", 2)[1:]
                token = json.dumps(key).encode("ascii")
                partial = b'"\\u00' + bytes([ord(key[0])]).hex().encode() + key[1:].encode() + b'"'
                first = token if form[0] == "literal" else partial
                member = first + b":" + json.dumps(target[key]).encode() + b","
                self.assertIn(member, raw)
                repaired = raw.replace(member, b"", 1)
                if form[1] == "literal":
                    self.assertEqual(
                        repaired,
                        json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("ascii"),
                    )
                    self.assertTrue(
                        consumer.validate(repaired, now_ms=1050)["declaration_checks_passed"]
                    )
                else:
                    self.assertEqual(repaired, self.controls[level + "_" + form[1]][0])
        with patch.object(consumer.subprocess, "run", return_value=self.good) as run:
            self.assertEqual(consumer.check_declaration_escaped_key_duplicates(self.case), 24)
        self.assertEqual(run.call_count, 24)
        for call, raw in zip(run.call_args_list, self.cases.values()):
            self.assertEqual(
                call.args[0],
                [consumer.sys.executable, "-I", "-m", "qualification", "--now-ms", "1050"],
            )
            self.assertEqual(
                call.kwargs, {"input": raw, "capture_output": True, "check": False, "timeout": 10}
            )
        self.assertEqual(self.case, original)

    def test_every_duplicate_requires_fixed_library_rejection(self):
        for name, raw in self.cases.items():
            for error in (None, ValueError("PRIVATE")):
                with self.subTest(case=name, error=error):
                    with (
                        patch.object(
                            consumer, "declaration_escaped_key_duplicates", return_value={name: raw}
                        ),
                        patch.object(
                            consumer, "validate", side_effect=error, return_value={}
                        ) as validate,
                        patch.object(consumer.subprocess, "run") as run,
                    ):
                        suffix = "missing" if error is None else "mismatch"
                        with self.assertRaisesRegex(
                            AssertionError,
                            "^declaration_escaped_key_error_" + suffix + ":" + name + "$",
                        ):
                            consumer.check_declaration_escaped_key_duplicates(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    run.assert_not_called()

    def test_every_duplicate_requires_fixed_process_rejection(self):
        for name, raw in self.cases.items():
            for field, value in (
                ("returncode", 0),
                ("returncode", 1),
                ("stdout", raw),
                ("stdout", b"{}"),
                ("stderr", b""),
                ("stderr", self.good.stderr + b"PRIVATE"),
                ("stderr", b"Traceback"),
            ):
                with self.subTest(case=name, field=field):
                    result = copy.copy(self.good)
                    setattr(result, field, value)
                    with (
                        patch.object(
                            consumer, "declaration_escaped_key_duplicates", return_value={name: raw}
                        ),
                        patch.object(consumer, "validate", wraps=consumer.validate) as validate,
                        patch.object(consumer.subprocess, "run", return_value=result) as run,
                    ):
                        with self.assertRaisesRegex(
                            AssertionError,
                            "^declaration_escaped_duplicate_process_mismatch:" + name + "$",
                        ):
                            consumer.check_declaration_escaped_key_duplicates(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    self.assert_process_call(run, raw)


class DeclarationUnicodeValueTests(unittest.TestCase):
    assert_process_call = DeclarationCollectionBoundaryTests.assert_process_call

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        self.doc = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        paths = {
            "rig_id": ("rig", "id"),
            "rig_configuration": ("rig", "configuration_sha256"),
            "sensor_id": ("rig", "sensors", 0, "id"),
            "sensor_device": ("rig", "sensors", 0, "device_sha256"),
            "sensor_mount": ("rig", "sensors", 0, "mount_sha256"),
            "capture_clock": ("capture", "clock_domain"),
            "record_sensor": ("records", 0, "sensor_id"),
            "record_clock": ("records", 0, "clock_domain"),
            "record_artifact": ("records", 0, "artifact_sha256"),
            "record_rig": ("records", 0, "rig_sha256"),
        }
        # Encode code points independently; the installed checker uses raw JSON
        # escape bytes. Paired surrogates decode to one non-ASCII scalar.
        values = {
            "high_min": chr(0xD800),
            "high_max": chr(0xDBFF),
            "low_min": chr(0xDC00),
            "low_max": chr(0xDFFF),
            "pair_min": chr(0x10000),
            "pair_max": chr(0x10FFFF),
            "reversed_pair": chr(0xDC00) + chr(0xD800),
            "high_ascii": chr(0xD800) + "a",
        }
        escapes = {name: json.dumps(value)[1:-1].encode() for name, value in values.items()}
        escapes["high_ascii"] = escapes["high_ascii"][:-1] + b"\\u0061"
        escapes.update(
            short_escape=b"\\u123",
            empty_escape=b"\\u",
            nonhex_escape=b"\\u12x4",
            uppercase_prefix=b"\\U0061",
        )
        self.cases, self.details = {}, {}
        for name, path in paths.items():
            doc = copy.deepcopy(self.doc)
            obj = doc
            for part in path[:-1]:
                obj = obj[part]
            original = obj[path[-1]]
            obj[path[-1]] = "UNICODE_VALUE_PLACEHOLDER"
            template = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
            marker = b'"UNICODE_VALUE_PLACEHOLDER"'
            self.assertEqual(template.count(marker), 1)
            for form, escape in escapes.items():
                value = b'"' + original[:-1].encode() + escape + b'"'
                raw = template.replace(marker, value)
                key = name + "_" + form
                self.cases[key] = raw
                self.details[key] = path, original, template, marker, values.get(form)
        self.good = SimpleNamespace(
            returncode=2,
            stdout=b"",
            stderr=("invalid_qualification_manifest" + os.linesep).encode("ascii"),
        )

    def test_independent_documents_and_full_binary_traversal(self):
        original = copy.deepcopy(self.case)
        self.assertEqual(consumer.declaration_unicode_value_inputs(self.case), self.cases)
        self.assertEqual(len(self.cases), 120)
        self.assertEqual(len(set(self.cases.values())), 120)
        with patch.object(consumer.subprocess, "run", return_value=self.good) as run:
            self.assertEqual(consumer.check_declaration_unicode_value_inputs(self.case), 120)
        self.assertEqual(run.call_count, 120)
        for call, raw in zip(run.call_args_list, self.cases.values()):
            self.assertLessEqual(len(raw), 65536)
            self.assertEqual(
                call.args[0],
                [consumer.sys.executable, "-I", "-m", "qualification", "--now-ms", "1050"],
            )
            self.assertEqual(
                call.kwargs, {"input": raw, "capture_output": True, "check": False, "timeout": 10}
            )
        self.assertEqual(self.case, original)

    def test_syntax_schema_boundaries_and_single_value_repairs(self):
        for name, raw in self.cases.items():
            path, original, template, marker, decoded_suffix = self.details[name]
            with self.subTest(case=name):
                if decoded_suffix is None:
                    with self.assertRaises(json.JSONDecodeError):
                        json.loads(raw)
                else:
                    decoded = json.loads(raw)
                    obj = decoded
                    for part in path[:-1]:
                        obj = obj[part]
                    self.assertEqual(obj[path[-1]], original[:-1] + decoded_suffix)
                    obj[path[-1]] = original
                    self.assertEqual(decoded, self.doc)
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
                    consumer.validate(raw, now_ms=1050)
                # An escaped ASCII last character repairs only the bad value;
                # references, rig commitments and every other member stay intact.
                repaired_value = ('"' + original[:-1] + '\\u%04x"' % ord(original[-1])).encode()
                repaired = template.replace(marker, repaired_value)
                self.assertEqual(json.loads(repaired), self.doc)
                report = consumer.validate(repaired, now_ms=1050)
                self.assertTrue(report["declaration_checks_passed"])
                self.assertFalse(report["artifacts_verified"])
                self.assertFalse(report["physical_qualification_passed"])
                self.assertEqual(report["input_sha256"], hashlib.sha256(repaired).hexdigest())

    def test_every_value_requires_fixed_library_rejection(self):
        for name, raw in self.cases.items():
            for error in (None, ValueError("PRIVATE")):
                with self.subTest(case=name, error=error):
                    with (
                        patch.object(
                            consumer, "declaration_unicode_value_inputs", return_value={name: raw}
                        ),
                        patch.object(
                            consumer, "validate", side_effect=error, return_value={}
                        ) as validate,
                        patch.object(consumer.subprocess, "run") as run,
                    ):
                        suffix = "missing" if error is None else "mismatch"
                        with self.assertRaisesRegex(
                            AssertionError,
                            "^declaration_unicode_error_" + suffix + ":" + name + "$",
                        ):
                            consumer.check_declaration_unicode_value_inputs(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    run.assert_not_called()

    def test_every_value_requires_fixed_process_rejection(self):
        for name, raw in self.cases.items():
            for field, value in (
                ("returncode", 0),
                ("returncode", 1),
                ("stdout", raw),
                ("stdout", b"{}"),
                ("stderr", b""),
                ("stderr", self.good.stderr + b"PRIVATE"),
                ("stderr", b"Traceback"),
            ):
                with self.subTest(case=name, field=field):
                    result = copy.copy(self.good)
                    setattr(result, field, value)
                    with (
                        patch.object(
                            consumer, "declaration_unicode_value_inputs", return_value={name: raw}
                        ),
                        patch.object(consumer, "validate", wraps=consumer.validate) as validate,
                        patch.object(consumer.subprocess, "run", return_value=result) as run,
                    ):
                        with self.assertRaisesRegex(
                            AssertionError, "^declaration_unicode_process_mismatch:" + name + "$"
                        ):
                            consumer.check_declaration_unicode_value_inputs(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    self.assert_process_call(run, raw)


def utf8_value_documents(case):
    """Independent placeholder encoding and code-point-based invalid byte table."""
    doc = json.loads(bytes.fromhex(case["captures"][0]["manifest_hex"]))
    paths = {
        "rig_id": ("rig", "id"),
        "rig_configuration": ("rig", "configuration_sha256"),
        "sensor_id": ("rig", "sensors", 0, "id"),
        "sensor_device": ("rig", "sensors", 0, "device_sha256"),
        "sensor_mount": ("rig", "sensors", 0, "mount_sha256"),
        "capture_clock": ("capture", "clock_domain"),
        "record_sensor": ("records", 0, "sensor_id"),
        "record_clock": ("records", 0, "clock_domain"),
        "record_artifact": ("records", 0, "artifact_sha256"),
        "record_rig": ("records", 0, "rig_sha256"),
    }
    values = {
        "overlong_2": bytes([0xC0 | (ord("a") >> 6), 0x80 | (ord("a") & 0x3F)]),
        "overlong_3": bytes([0xE0, 0x80 | (ord("a") >> 6), 0x80 | (ord("a") & 0x3F)]),
        "overlong_4": bytes([0xF0, 0x80, 0x80 | (ord("a") >> 6), 0x80 | (ord("a") & 0x3F)]),
        **{
            name: chr(point).encode("utf-8", errors="surrogatepass")
            for name, point in (
                ("high_min", 0xD800),
                ("high_max", 0xDBFF),
                ("low_min", 0xDC00),
                ("low_max", 0xDFFF),
            )
        },
        "continuation_min": bytes([128]),
        "continuation_max": bytes([191]),
        "truncated_2": chr(0x80).encode("utf-8")[:1],
        **{"truncated_3_" + str(n): chr(0x1000).encode("utf-8")[:n] for n in (1, 2)},
        **{"truncated_4_" + str(n): chr(0x40000).encode("utf-8")[:n] for n in (1, 2, 3)},
        "out_of_range": bytes([244, 144, 128, 128]),
        "invalid_lead": bytes([255]),
        "invalid_continuation": bytes([225, ord("a"), 128]),
    }
    controls, cases, details = {}, {}, {}
    for name, path in paths.items():
        changed = copy.deepcopy(doc)
        obj = changed
        for part in path[:-1]:
            obj = obj[part]
        original = obj[path[-1]]
        obj[path[-1]] = "UTF8_VALUE_PLACEHOLDER"
        marker = b'"UTF8_VALUE_PLACEHOLDER"'
        template = json.dumps(changed, sort_keys=True, separators=(",", ":")).encode("ascii")
        assert template.count(marker) == 1
        prefix = b'"' + original[:-1].encode("ascii")
        repair = b"\\u00" + original[-1:].encode("ascii").hex().encode("ascii")
        repaired = template.replace(marker, prefix + repair + b'"')
        controls[name] = (
            repaired,
            {
                "version": 1,
                "input_sha256": hashlib.sha256(repaired).hexdigest(),
                "declaration_checks_passed": True,
                "sensor_count": 2,
                "record_count": 6,
                "evidence_counts": {"synthetic": 6, "recorded": 0, "external_unverified": 0},
                "findings": [],
                "artifacts_verified": False,
                "physical_qualification_passed": False,
                "physical_status": "blocked_external_evidence_and_review",
            },
        )
        for form, suffix in values.items():
            key = name + "_" + form
            raw = template.replace(marker, prefix + suffix + b'"')
            cases[key] = raw
            details[key] = name, suffix, repair, path, original
    return controls, cases, details


class DeclarationUTF8ValueControlTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_utf8_value_controls)
    check = staticmethod(consumer.check_declaration_utf8_value_controls)
    diagnostic = "declaration_utf8_"
    count = 10

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        self.cases, _, _ = utf8_value_documents(self.case)

    def test_repairs_preserve_semantics_and_stale_findings(self):
        doc = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        self.assertEqual(len({raw for raw, _ in self.cases.values()}), 10)
        for raw, report in self.cases.values():
            self.assertEqual(json.loads(raw), doc)
            self.assertNotEqual(
                report["input_sha256"], hashlib.sha256(self.encode(doc)).hexdigest()
            )
        stale = next(case for case in consumer.corpus(CORPUS) if case["id"] == "stale")
        for raw, report in self.generate(stale).values():
            self.assertEqual(report["findings"], ["capture_stale"])
            self.assertFalse(report["declaration_checks_passed"])
            self.assertEqual(self.encode(consumer.validate(raw, now_ms=1151)), self.encode(report))


class DeclarationUTF8ValueTests(unittest.TestCase):
    assert_process_call = DeclarationCollectionBoundaryTests.assert_process_call

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        self.controls, self.cases, self.details = utf8_value_documents(self.case)
        self.good = SimpleNamespace(
            returncode=2,
            stdout=b"",
            stderr=("invalid_qualification_manifest" + os.linesep).encode("ascii"),
        )

    def test_independent_documents_and_full_binary_traversal(self):
        original = copy.deepcopy(self.case)
        self.assertEqual(consumer.declaration_utf8_value_inputs(self.case), self.cases)
        self.assertEqual(len(self.cases), 180)
        self.assertEqual(len(set(self.cases.values())), 180)
        with patch.object(consumer.subprocess, "run", return_value=self.good) as run:
            self.assertEqual(consumer.check_declaration_utf8_value_inputs(self.case), 180)
        self.assertEqual(run.call_count, 180)
        for call, raw in zip(run.call_args_list, self.cases.values()):
            self.assertLessEqual(len(raw), 65536)
            self.assertEqual(
                call.args[0],
                [consumer.sys.executable, "-I", "-m", "qualification", "--now-ms", "1050"],
            )
            self.assertEqual(
                call.kwargs, {"input": raw, "capture_output": True, "check": False, "timeout": 10}
            )
        self.assertEqual(self.case, original)

    def test_invalid_encoding_and_single_value_repairs(self):
        doc = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        for name, raw in self.cases.items():
            field, suffix, repair, path, original = self.details[name]
            with self.subTest(case=name):
                with self.assertRaises(UnicodeDecodeError):
                    raw.decode("utf-8")
                if suffix.startswith(b"\xed"):
                    # json.loads(bytes) permits encoded surrogates; the
                    # validator must retain its explicit strict UTF-8 decode.
                    decoded = json.loads(raw)
                    obj = decoded
                    for part in path[:-1]:
                        obj = obj[part]
                    self.assertEqual(
                        obj[path[-1]], original[:-1] + suffix.decode("utf-8", "surrogatepass")
                    )
                    obj[path[-1]] = original
                    self.assertEqual(decoded, doc)
                else:
                    with self.assertRaises(UnicodeDecodeError):
                        json.loads(raw)
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
                    consumer.validate(raw, now_ms=1050)
                # Invalid bytes are confined to the final character of one
                # value; restoring it yields the exact independent control.
                self.assertEqual(raw.count(suffix), 1)
                repaired = raw.replace(suffix, repair, 1)
                expected_raw, report = self.controls[field]
                self.assertEqual(repaired, expected_raw)
                self.assertEqual(json.loads(repaired), doc)
                self.assertEqual(
                    consumer.canonical(consumer.validate(repaired, now_ms=1050)),
                    consumer.canonical(report),
                )
                # Even a permissive replacement decoder cannot hide another
                # malformed member in the surrounding JSON document.
                lossy = json.loads(raw.decode("utf-8", errors="replace"))
                obj = lossy
                for part in path[:-1]:
                    obj = obj[part]
                self.assertIn("\ufffd", obj[path[-1]])
                obj[path[-1]] = original
                self.assertEqual(lossy, doc)

    def test_every_value_requires_fixed_library_rejection(self):
        for name, raw in self.cases.items():
            for error in (None, ValueError("PRIVATE")):
                with self.subTest(case=name, error=error):
                    with (
                        patch.object(
                            consumer, "declaration_utf8_value_inputs", return_value={name: raw}
                        ),
                        patch.object(
                            consumer, "validate", side_effect=error, return_value={}
                        ) as validate,
                        patch.object(consumer.subprocess, "run") as run,
                    ):
                        suffix = "missing" if error is None else "mismatch"
                        with self.assertRaisesRegex(
                            AssertionError,
                            "^declaration_utf8_error_" + suffix + ":" + name + "$",
                        ):
                            consumer.check_declaration_utf8_value_inputs(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    run.assert_not_called()

    def test_every_value_requires_fixed_process_rejection(self):
        for name, raw in self.cases.items():
            for field, value in (
                ("returncode", 0),
                ("returncode", 1),
                ("stdout", raw),
                ("stdout", b"{}"),
                ("stderr", b""),
                ("stderr", self.good.stderr + b"PRIVATE"),
                ("stderr", b"Traceback"),
            ):
                with self.subTest(case=name, field=field):
                    result = copy.copy(self.good)
                    setattr(result, field, value)
                    with (
                        patch.object(
                            consumer, "declaration_utf8_value_inputs", return_value={name: raw}
                        ),
                        patch.object(consumer, "validate", wraps=consumer.validate) as validate,
                        patch.object(consumer.subprocess, "run", return_value=result) as run,
                    ):
                        with self.assertRaisesRegex(
                            AssertionError, "^declaration_utf8_rejection_mismatch:" + name + "$"
                        ):
                            consumer.check_declaration_utf8_value_inputs(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    self.assert_process_call(run, raw)


class DeclarationEncodingControlTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_encoding_controls)
    check = staticmethod(consumer.check_declaration_encoding_controls)
    diagnostic = "declaration_encoding_"
    count = 1

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        doc = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        self.cases = {}
        self.save("utf8", doc, 2, 6, [])

    def test_stale_control_preserves_report_and_binary_exit_status(self):
        stale = next(case for case in consumer.corpus(CORPUS) if case["id"] == "stale")
        raw, report = self.cases["utf8"]
        report = dict(report, findings=["capture_stale"], declaration_checks_passed=False)
        self.assertEqual(self.generate(stale), {"utf8": (raw, report)})
        with patch.object(consumer.subprocess, "run", return_value=self.result(report)) as run:
            self.assertEqual(self.check(stale), 1)
        run.assert_called_once_with(
            [consumer.sys.executable, "-I", "-m", "qualification", "--now-ms", "1151"],
            input=raw,
            capture_output=True,
            check=False,
            timeout=10,
        )


class DeclarationAlternateEncodingTests(unittest.TestCase):
    assert_process_call = DeclarationCollectionBoundaryTests.assert_process_call

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        self.doc = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        self.raw = json.dumps(self.doc, sort_keys=True, separators=(",", ":")).encode("ascii")
        # Build ASCII code units independently of the generator's text codecs.
        self.cases = {"utf8_bom": bytes([239, 187, 191]) + self.raw}
        for width in (2, 4):
            for order, suffix in (("little", "le"), ("big", "be")):
                name = "utf" + str(width * 8) + suffix
                raw = b"".join(value.to_bytes(width, order) for value in self.raw)
                self.cases[name] = raw
                self.cases[name + "_bom"] = (0xFEFF).to_bytes(width, order) + raw
        self.good = SimpleNamespace(
            returncode=2,
            stdout=b"",
            stderr=("invalid_qualification_manifest" + os.linesep).encode("ascii"),
        )

    def test_independent_encodings_and_full_binary_traversal(self):
        original = copy.deepcopy(self.case)
        self.assertEqual(consumer.declaration_alternate_encodings(self.case), self.cases)
        self.assertEqual(len(set(self.cases.values())), 9)
        with patch.object(consumer.subprocess, "run", return_value=self.good) as run:
            self.assertEqual(consumer.check_declaration_alternate_encodings(self.case), 9)
        self.assertEqual(run.call_count, 9)
        for call, raw in zip(run.call_args_list, self.cases.values()):
            self.assertLessEqual(len(raw), 65536)
            self.assertEqual(
                call.args[0],
                [consumer.sys.executable, "-I", "-m", "qualification", "--now-ms", "1050"],
            )
            self.assertEqual(
                call.kwargs, {"input": raw, "capture_output": True, "check": False, "timeout": 10}
            )
        self.assertEqual(self.case, original)

    def test_autodetection_accepts_each_document_but_validator_requires_utf8(self):
        control, report = consumer.declaration_encoding_controls(self.case)["utf8"]
        self.assertEqual(control, self.raw)
        for name, raw in self.cases.items():
            with self.subTest(case=name):
                # These are valid JSON documents under alternate encodings,
                # not schema failures or oversized/truncated input.
                self.assertEqual(json.loads(raw), self.doc)
                repaired = json.dumps(
                    json.loads(raw), sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                self.assertEqual(repaired, control)
                self.assertNotEqual(hashlib.sha256(raw).hexdigest(), report["input_sha256"])
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
                    consumer.validate(raw, now_ms=1050)
                self.assertEqual(
                    consumer.canonical(consumer.validate(repaired, now_ms=1050)),
                    consumer.canonical(report),
                )

    def test_every_encoding_requires_fixed_library_rejection(self):
        for name, raw in self.cases.items():
            for error in (None, ValueError("PRIVATE")):
                with self.subTest(case=name, error=error):
                    with (
                        patch.object(
                            consumer, "declaration_alternate_encodings", return_value={name: raw}
                        ),
                        patch.object(
                            consumer, "validate", side_effect=error, return_value={}
                        ) as validate,
                        patch.object(consumer.subprocess, "run") as run,
                    ):
                        suffix = "missing" if error is None else "mismatch"
                        with self.assertRaisesRegex(
                            AssertionError,
                            "^declaration_encoding_error_" + suffix + ":" + name + "$",
                        ):
                            consumer.check_declaration_alternate_encodings(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    run.assert_not_called()

    def test_every_encoding_requires_fixed_process_rejection(self):
        for name, raw in self.cases.items():
            for field, value in (
                ("returncode", 0),
                ("returncode", 1),
                ("stdout", raw),
                ("stdout", b"{}"),
                ("stderr", b""),
                ("stderr", self.good.stderr + b"PRIVATE"),
                ("stderr", b"Traceback"),
            ):
                with self.subTest(case=name, field=field):
                    result = copy.copy(self.good)
                    setattr(result, field, value)
                    with (
                        patch.object(
                            consumer, "declaration_alternate_encodings", return_value={name: raw}
                        ),
                        patch.object(consumer, "validate", wraps=consumer.validate) as validate,
                        patch.object(consumer.subprocess, "run", return_value=result) as run,
                    ):
                        with self.assertRaisesRegex(
                            AssertionError,
                            "^declaration_encoding_rejection_mismatch:" + name + "$",
                        ):
                            consumer.check_declaration_alternate_encodings(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    self.assert_process_call(run, raw)


def whitespace_tokens(value):
    """Independent recursive serialization, without the consumer's regex lexer."""
    if isinstance(value, dict):
        yield b"{"
        for index, key in enumerate(sorted(value)):
            if index:
                yield b","
            yield json.dumps(key).encode("ascii")
            yield b":"
            yield from whitespace_tokens(value[key])
        yield b"}"
    elif isinstance(value, list):
        yield b"["
        for index, item in enumerate(value):
            if index:
                yield b","
            yield from whitespace_tokens(item)
        yield b"]"
    else:
        yield json.dumps(value).encode("ascii")


class DeclarationWhitespaceControlTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_whitespace_controls)
    check = staticmethod(consumer.check_declaration_whitespace_controls)
    diagnostic = "declaration_whitespace_"
    count = 21

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        self.doc = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        tokens = list(whitespace_tokens(self.doc))
        raw = b"".join(tokens)
        self.cases = {}
        for name, codes in (
            ("space", [32]),
            ("tab", [9]),
            ("lf", [10]),
            ("crlf", [13, 10]),
            ("mixed", [32, 9, 10, 13, 10]),
        ):
            separator = bytes(codes)
            for position in ("leading", "trailing", "between", "all"):
                value = separator.join(tokens) if position in ("between", "all") else raw
                if position in ("leading", "all"):
                    value = separator + value
                if position in ("trailing", "all"):
                    value += separator
                self.save(name + "_" + position, self.doc, 2, 6, [])
                _, report = self.cases[name + "_" + position]
                report["input_sha256"] = hashlib.sha256(value).hexdigest()
                self.cases[name + "_" + position] = value, report
        index = raw.index(b":") + 1
        self.save("space_after_colon", self.doc, 2, 6, [])
        _, report = self.cases["space_after_colon"]
        value = raw[:index] + bytes([32]) + raw[index:]
        report["input_sha256"] = hashlib.sha256(value).hexdigest()
        self.cases["space_after_colon"] = value, report

    def test_whitespace_preserves_values_and_commits_each_byte_layout(self):
        self.assertEqual(len({raw for raw, _ in self.cases.values()}), self.count)
        for name, (raw, expected) in self.cases.items():
            with self.subTest(case=name):
                self.assertEqual(json.loads(raw), self.doc)
                self.assertEqual(
                    consumer.canonical(consumer.validate(raw, now_ms=1050)),
                    consumer.canonical(expected),
                )
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected["input_sha256"])

    def test_all_stale_layouts_preserve_findings_and_binary_exit_status(self):
        stale = next(case for case in consumer.corpus(CORPUS) if case["id"] == "stale")
        expected = {
            name: (raw, dict(report, findings=["capture_stale"], declaration_checks_passed=False))
            for name, (raw, report) in self.cases.items()
        }
        self.assertEqual(self.generate(stale), expected)
        with patch.object(
            consumer.subprocess, "run", side_effect=[self.result(r) for _, r in expected.values()]
        ) as run:
            self.assertEqual(self.check(stale), self.count)
        self.assertEqual(run.call_count, self.count)
        for call, (raw, _) in zip(run.call_args_list, expected.values()):
            self.assertEqual(
                call.args[0],
                [consumer.sys.executable, "-I", "-m", "qualification", "--now-ms", "1151"],
            )
            self.assertEqual(
                call.kwargs, {"input": raw, "capture_output": True, "check": False, "timeout": 10}
            )


class DeclarationInvalidSeparatorTests(unittest.TestCase):
    assert_process_call = DeclarationCollectionBoundaryTests.assert_process_call

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        doc = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        self.raw = b"".join(whitespace_tokens(doc))
        self.cases = {}
        self.repairs = {}
        for name, separator in (("vt", chr(11)), ("ff", chr(12)), ("nbsp", chr(160))):
            for position, index in (
                ("leading", 0),
                ("trailing", len(self.raw)),
                ("after_colon", self.raw.index(b":") + 1),
            ):
                key = name + "_" + position
                self.cases[key] = self.raw[:index] + separator.encode("utf-8") + self.raw[index:]
                self.repairs[key] = (index, len(separator.encode("utf-8")), "space_" + position)
        self.good = SimpleNamespace(
            returncode=2,
            stdout=b"",
            stderr=("invalid_qualification_manifest" + os.linesep).encode("ascii"),
        )

    def test_independent_separators_and_full_binary_traversal(self):
        original = copy.deepcopy(self.case)
        self.assertEqual(consumer.declaration_invalid_separators(self.case), self.cases)
        self.assertEqual(len(set(self.cases.values())), 9)
        with patch.object(consumer.subprocess, "run", return_value=self.good) as run:
            self.assertEqual(consumer.check_declaration_invalid_separators(self.case), 9)
        self.assertEqual(run.call_count, 9)
        for call, raw in zip(run.call_args_list, self.cases.values()):
            self.assertLessEqual(len(raw), 65536)
            self.assertEqual(
                call.args[0],
                [consumer.sys.executable, "-I", "-m", "qualification", "--now-ms", "1050"],
            )
            self.assertEqual(
                call.kwargs, {"input": raw, "capture_output": True, "check": False, "timeout": 10}
            )
        self.assertEqual(self.case, original)

    def test_only_one_separator_needs_repair_for_passing_and_stale_reports(self):
        for case in consumer.corpus(CORPUS):
            if case["id"] not in ("complete", "stale"):
                continue
            controls = consumer.declaration_whitespace_controls(case)
            for name, raw in self.cases.items():
                with self.subTest(case=case["id"], separator=name):
                    # Every document is valid UTF-8 but invalid JSON syntax.
                    with self.assertRaises(json.JSONDecodeError):
                        json.loads(raw.decode("utf-8"))
                    index, length, control = self.repairs[name]
                    repaired = raw[:index] + b" " + raw[index + length :]
                    expected_raw, report = controls[control]
                    self.assertEqual(repaired, expected_raw)
                    instant = case["captures"][0]["now_ms"]
                    with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
                        consumer.validate(raw, now_ms=instant)
                    self.assertEqual(
                        consumer.canonical(consumer.validate(repaired, now_ms=instant)),
                        consumer.canonical(report),
                    )

    def test_every_separator_requires_fixed_library_rejection(self):
        for name, raw in self.cases.items():
            for error in (None, ValueError("PRIVATE")):
                with self.subTest(case=name, error=error):
                    with (
                        patch.object(
                            consumer, "declaration_invalid_separators", return_value={name: raw}
                        ),
                        patch.object(
                            consumer, "validate", side_effect=error, return_value={}
                        ) as validate,
                        patch.object(consumer.subprocess, "run") as run,
                    ):
                        suffix = "missing" if error is None else "mismatch"
                        with self.assertRaisesRegex(
                            AssertionError,
                            "^declaration_whitespace_error_" + suffix + ":" + name + "$",
                        ):
                            consumer.check_declaration_invalid_separators(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    run.assert_not_called()

    def test_every_separator_requires_fixed_process_rejection(self):
        for name, raw in self.cases.items():
            for field, value in (
                ("returncode", 0),
                ("returncode", 1),
                ("stdout", raw),
                ("stdout", b"{}"),
                ("stderr", b""),
                ("stderr", self.good.stderr + b"PRIVATE"),
                ("stderr", b"Traceback"),
            ):
                with self.subTest(case=name, field=field):
                    result = copy.copy(self.good)
                    setattr(result, field, value)
                    with (
                        patch.object(
                            consumer, "declaration_invalid_separators", return_value={name: raw}
                        ),
                        patch.object(consumer, "validate", wraps=consumer.validate) as validate,
                        patch.object(consumer.subprocess, "run", return_value=result) as run,
                    ):
                        with self.assertRaisesRegex(
                            AssertionError,
                            "^declaration_whitespace_rejection_mismatch:" + name + "$",
                        ):
                            consumer.check_declaration_invalid_separators(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    self.assert_process_call(run, raw)


class DeclarationInvalidPunctuationTests(unittest.TestCase):
    assert_process_call = DeclarationCollectionBoundaryTests.assert_process_call

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        self.doc = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        output = bytearray()
        marks = {}

        def emit(value, path=()):
            if not isinstance(value, (dict, list)):
                output.extend(json.dumps(value).encode("ascii"))
                return
            marks[path] = {"colon": [], "comma": []}
            mapping = isinstance(value, dict)
            output.extend(b"{" if mapping else b"[")
            entries = sorted(value.items()) if mapping else list(enumerate(value))
            for index, (key, item) in enumerate(entries):
                if index:
                    marks[path]["comma"].append(len(output))
                    output.extend(b",")
                if mapping:
                    output.extend(json.dumps(key).encode("ascii"))
                    marks[path]["colon"].append(len(output))
                    output.extend(b":")
                emit(item, path + (key,))
            marks[path]["close"] = len(output)
            output.extend(b"}" if mapping else b"]")

        emit(self.doc)
        self.raw = bytes(output)
        paths = {
            "root": (),
            "rig": ("rig",),
            "sensor": ("rig", "sensors", 0),
            "capture": ("capture",),
            "record": ("records", 0),
        }
        for kind in ("calibration", "clock", "environment"):
            index = next(i for i, row in enumerate(self.doc["records"]) if row["kind"] == kind)
            paths["data_" + kind] = ("records", index, "data")
        paths.update(sensors=("rig", "sensors"), records=("records",))
        self.cases, self.repairs = {}, {}
        for name, path in paths.items():
            for kind in ("colon", "comma"):
                if not marks[path][kind]:
                    continue
                index = marks[path][kind][0]
                token = self.raw[index : index + 1]
                key = name + "_" + kind + "_missing"
                self.cases[key] = self.raw[:index] + self.raw[index + 1 :]
                self.repairs[key] = (index, True, token)
                key = name + "_" + kind + "_doubled"
                self.cases[key] = self.raw[:index] + token + self.raw[index:]
                self.repairs[key] = (index, False, token)
            key = name + "_trailing_comma"
            index = marks[path]["close"]
            self.cases[key] = self.raw[:index] + b"," + self.raw[index:]
            self.repairs[key] = (index, False, b",")
        self.good = SimpleNamespace(
            returncode=2,
            stdout=b"",
            stderr=("invalid_qualification_manifest" + os.linesep).encode("ascii"),
        )

    def test_independent_punctuation_and_full_binary_traversal(self):
        original = copy.deepcopy(self.case)
        self.assertEqual(consumer.declaration_invalid_punctuation(self.case), self.cases)
        self.assertEqual(len(set(self.cases.values())), 46)
        with patch.object(consumer.subprocess, "run", return_value=self.good) as run:
            self.assertEqual(consumer.check_declaration_invalid_punctuation(self.case), 46)
        self.assertEqual(run.call_count, 46)
        for call, raw in zip(run.call_args_list, self.cases.values()):
            self.assertLessEqual(len(raw), 65536)
            self.assertEqual(
                call.args[0],
                [consumer.sys.executable, "-I", "-m", "qualification", "--now-ms", "1050"],
            )
            self.assertEqual(
                call.kwargs, {"input": raw, "capture_output": True, "check": False, "timeout": 10}
            )
        self.assertEqual(self.case, original)

    def test_single_token_repairs_reach_passing_and_stale_reports(self):
        for case in consumer.corpus(CORPUS):
            if case["id"] not in ("complete", "stale"):
                continue
            self.assertEqual(consumer.declaration_invalid_punctuation(case), self.cases)
            expected_raw, report = consumer.declaration_encoding_controls(case)["utf8"]
            instant = case["captures"][0]["now_ms"]
            for name, raw in self.cases.items():
                with self.subTest(case=case["id"], punctuation=name):
                    with self.assertRaises(json.JSONDecodeError):
                        json.loads(raw.decode("utf-8"))
                    with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
                        consumer.validate(raw, now_ms=instant)
                    index, insert, token = self.repairs[name]
                    repaired = (
                        raw[:index] + token + raw[index:]
                        if insert
                        else raw[:index] + raw[index + 1 :]
                    )
                    self.assertEqual(repaired, self.raw)
                    self.assertEqual(repaired, expected_raw)
                    self.assertEqual(json.loads(repaired), self.doc)
                    self.assertEqual(
                        consumer.canonical(consumer.validate(repaired, now_ms=instant)),
                        consumer.canonical(report),
                    )
                    self.assertEqual(
                        report["findings"], [] if case["id"] == "complete" else ["capture_stale"]
                    )
                    self.assertIs(report["physical_qualification_passed"], False)
                    self.assertIs(report["artifacts_verified"], False)

    def test_every_punctuation_requires_fixed_library_rejection(self):
        for name, raw in self.cases.items():
            for error in (None, ValueError("PRIVATE")):
                with self.subTest(case=name, error=error):
                    with (
                        patch.object(
                            consumer, "declaration_invalid_punctuation", return_value={name: raw}
                        ),
                        patch.object(
                            consumer, "validate", side_effect=error, return_value={}
                        ) as validate,
                        patch.object(consumer.subprocess, "run") as run,
                    ):
                        suffix = "missing" if error is None else "mismatch"
                        with self.assertRaisesRegex(
                            AssertionError,
                            "^declaration_punctuation_error_" + suffix + ":" + name + "$",
                        ):
                            consumer.check_declaration_invalid_punctuation(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    run.assert_not_called()

    def test_every_punctuation_requires_fixed_process_rejection(self):
        for name, raw in self.cases.items():
            for field, value in (
                ("returncode", 0),
                ("returncode", 1),
                ("stdout", raw),
                ("stdout", b"{}"),
                ("stderr", b""),
                ("stderr", self.good.stderr + b"PRIVATE"),
                ("stderr", b"Traceback"),
            ):
                with self.subTest(case=name, field=field):
                    result = copy.copy(self.good)
                    setattr(result, field, value)
                    with (
                        patch.object(
                            consumer, "declaration_invalid_punctuation", return_value={name: raw}
                        ),
                        patch.object(consumer, "validate", wraps=consumer.validate) as validate,
                        patch.object(consumer.subprocess, "run", return_value=result) as run,
                    ):
                        with self.assertRaisesRegex(
                            AssertionError,
                            "^declaration_punctuation_rejection_mismatch:" + name + "$",
                        ):
                            consumer.check_declaration_invalid_punctuation(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    self.assert_process_call(run, raw)


class DeclarationTokenBoundaryTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_token_boundaries)
    check = staticmethod(consumer.check_declaration_token_boundaries)
    diagnostic = "declaration_token_"
    count = 44

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        original = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        self.cases = {}
        # Independent token table and documents; reports use literal counts and
        # false authority flags from save(), never the validator's output.
        tokens = [
            ("lower_1", "a"),
            ("upper_1", "Z"),
            ("digit_1", "7"),
            ("underscore_1", "_"),
            ("hyphen_1", "-"),
            ("lower_64", "a" * 64),
            ("upper_64", "Z" * 64),
            ("digit_64", "7" * 64),
            ("underscore_64", "_" * 64),
            ("hyphen_64", "-" * 64),
            ("mixed_64", ("aZ7_-" * 13)[:64]),
        ]
        for field in ("rig", "sensor_0", "sensor_1", "domain"):
            for name, token in tokens:
                doc = copy.deepcopy(original)
                if field == "rig":
                    doc["rig"]["id"] = token
                elif field == "domain":
                    doc["capture"]["clock_domain"] = token
                    for record in doc["records"]:
                        record["clock_domain"] = token
                else:
                    index = 0 if field == "sensor_0" else 1
                    doc["rig"]["sensors"][index]["id"] = token
                    for record in doc["records"][index * 3 : index * 3 + 3]:
                        self.assertEqual(
                            record["sensor_id"], original["rig"]["sensors"][index]["id"]
                        )
                        record["sensor_id"] = token
                digest = hashlib.sha256(self.encode(doc["rig"])).hexdigest()
                for record in doc["records"]:
                    record["rig_sha256"] = digest
                self.save(field + "_" + name, doc, 2, 6, [])

    def test_token_admission_preserves_existing_calibration_failures(self):
        for name, (raw, expected) in self.cases.items():
            with self.subTest(case=name):
                doc = json.loads(raw)
                doc["records"][0]["data"]["valid_until_ms"] = 1049
                changed = self.encode(doc)
                report = copy.deepcopy(expected)
                report.update(
                    input_sha256=hashlib.sha256(changed).hexdigest(),
                    declaration_checks_passed=False,
                    findings=["calibration_interval"],
                )
                self.assertEqual(
                    self.encode(consumer.validate(changed, now_ms=1050)), self.encode(report)
                )


class DeclarationCaseReferenceTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_case_references)
    check = staticmethod(consumer.check_declaration_case_references)
    diagnostic = "declaration_case_reference_"
    count = 14

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        original = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        self.cases = {}
        doc = copy.deepcopy(original)
        for index, token in enumerate(("Sensor", "sensor")):
            doc["rig"]["sensors"][index]["id"] = token
            for record in doc["records"][index * 3 : index * 3 + 3]:
                record["sensor_id"] = token
        digest = hashlib.sha256(self.encode(doc["rig"])).hexdigest()
        for record in doc["records"]:
            record["rig_sha256"] = digest
        self.save("sensors_forward", doc, 2, 6, [])
        doc["records"] = list(reversed(doc["records"]))
        self.save("sensors_reverse", doc, 2, 6, [])
        for index in range(6):
            doc = copy.deepcopy(original)
            self.assertEqual(doc["capture"]["clock_domain"], "synthetic-boot")
            doc["records"][index]["clock_domain"] = "SYNTHETIC-BOOT"
            self.save(f"clock_{index}_mismatch", doc, 2, 6, ["clock_domain_mismatch"])
            doc["records"][index]["clock_domain"] = "synthetic-boot"
            self.save(f"clock_{index}_repaired", doc, 2, 6, [])

    def test_case_repairs_change_only_the_reference(self):
        for index in range(6):
            wrong, expected = self.cases[f"clock_{index}_mismatch"]
            repaired, passing = self.cases[f"clock_{index}_repaired"]
            self.assertEqual(expected["findings"], ["clock_domain_mismatch"])
            self.assertEqual(passing["findings"], [])
            doc = json.loads(wrong)
            doc["records"][index]["clock_domain"] = doc["capture"]["clock_domain"]
            self.assertEqual(self.encode(doc), repaired)


class DeclarationPartialRecordTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_partial_records)
    check = staticmethod(consumer.check_declaration_partial_records)
    diagnostic = "declaration_partial_record_"
    count = 12

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        doc = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        for index, token in enumerate(("Sensor", "sensor")):
            doc["rig"]["sensors"][index]["id"] = token
            for row in doc["records"][index * 3 : index * 3 + 3]:
                row["sensor_id"] = token
        digest = hashlib.sha256(self.encode(doc["rig"])).hexdigest()
        evidence = ("synthetic", "recorded", "external_unverified") * 2
        for row, kind in zip(doc["records"], evidence):
            row.update(rig_sha256=digest, evidence=kind)
        self.complete = doc
        self.cases = {}
        # Select by exact sensor/kind instead of the generator's positional removal.
        for sensor in ("Sensor", "sensor"):
            for kind, provenance in zip(("calibration", "clock", "environment"), evidence[:3]):
                for state in ("missing", "restored"):
                    changed = copy.deepcopy(doc)
                    missing = state == "missing"
                    if missing:
                        changed["records"] = [
                            row
                            for row in changed["records"]
                            if (row["sensor_id"], row["kind"]) != (sensor, kind)
                        ]
                    name = sensor + "_" + kind + "_" + state
                    self.save(
                        name,
                        changed,
                        2,
                        5 if missing else 6,
                        ["missing_" + kind] if missing else [],
                    )
                    self.cases[name][1]["evidence_counts"] = {
                        value: 1 if missing and value == provenance else 2 for value in evidence[:3]
                    }

    def test_restoring_only_the_missing_record_recovers_the_complete_report(self):
        for index, row in enumerate(self.complete["records"]):
            name = row["sensor_id"] + "_" + row["kind"]
            raw, expected = self.cases[name + "_missing"]
            restored, passing = self.cases[name + "_restored"]
            with self.subTest(case=name):
                doc = json.loads(raw)
                same_kind = [entry for entry in doc["records"] if entry["kind"] == row["kind"]]
                self.assertEqual(len(same_kind), 1)
                self.assertEqual(
                    same_kind[0]["sensor_id"],
                    "Sensor" if row["sensor_id"] == "sensor" else "sensor",
                )
                self.assertEqual(expected["findings"], ["missing_" + row["kind"]])
                self.assertFalse(expected["declaration_checks_passed"])
                doc["records"].insert(index, copy.deepcopy(row))
                self.assertEqual(doc, self.complete)
                self.assertEqual(self.encode(doc), restored)
                self.assertEqual(passing["findings"], [])
                self.assertTrue(passing["declaration_checks_passed"])
                self.assertEqual(
                    self.encode(consumer.validate(restored, now_ms=1050)), self.encode(passing)
                )


class DeclarationCombinedFailureTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_combined_failures)
    check = staticmethod(consumer.check_declaration_combined_failures)
    diagnostic = "declaration_combined_failure_"
    count = 72

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        doc = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        kinds = ("calibration", "clock", "environment")
        evidence = ("synthetic", "recorded", "external_unverified")
        for index, token in enumerate(("Sensor", "sensor")):
            doc["rig"]["sensors"][index]["id"] = token
            for row, provenance in zip(doc["records"][index * 3 : index * 3 + 3], evidence):
                row.update(sensor_id=token, evidence=provenance)
        digest = hashlib.sha256(self.encode(doc["rig"])).hexdigest()
        for row in doc["records"]:
            row["rig_sha256"] = digest
        self.complete = doc
        self.cases = {}
        self.repairs = {}
        # Independent selection and literal findings; do not derive reports from
        # the consumer generator or the validator under test.
        for sensor in ("Sensor", "sensor"):
            for missing_kind, provenance in zip(kinds, evidence):
                for bad_kind in kinds:
                    base = sensor + "_" + missing_kind + "_missing_" + bad_kind
                    for repair in ("none", "missing", "domain", "binding"):
                        changed = copy.deepcopy(doc)
                        if repair != "missing":
                            changed["records"] = [
                                row
                                for row in changed["records"]
                                if (row["sensor_id"], row["kind"]) != (sensor, missing_kind)
                            ]
                        bad = next(
                            row
                            for row in changed["records"]
                            if row["sensor_id"] != sensor and row["kind"] == bad_kind
                        )
                        if repair != "domain":
                            bad["clock_domain"] = "foreign_clock"
                        if repair != "binding":
                            bad["rig_sha256"] = "0" * 64
                        if bad_kind == "calibration":
                            bad["data"] = {"valid_from_ms": 0, "valid_until_ms": 0}
                        else:
                            bad["data"]["at_ms"] = 0
                            if bad_kind == "clock":
                                bad["data"].update(offset_ms=100, uncertainty_ms=1)
                        findings = []
                        if repair != "missing":
                            findings.append("missing_" + missing_kind)
                        if repair != "binding":
                            findings.append("rig_binding_mismatch")
                        if repair != "domain":
                            findings.append("clock_domain_mismatch")
                        elif bad_kind == "calibration":
                            findings.append("calibration_interval")
                        else:
                            findings.extend(["record_outside_capture", "record_stale"])
                            if bad_kind == "clock":
                                findings.append("clock_reference_skew")
                                if missing_kind != "clock":
                                    findings.append("clock_pair_skew")
                        name = base + "_repair_" + repair
                        self.save(
                            name, changed, 2, 6 if repair == "missing" else 5, sorted(findings)
                        )
                        self.cases[name][1]["evidence_counts"] = {
                            value: 1 if repair != "missing" and value == provenance else 2
                            for value in evidence
                        }
                    self.repairs[base] = sensor, missing_kind, bad_kind

    def test_each_repair_changes_only_one_defect(self):
        for base, (sensor, missing_kind, bad_kind) in self.repairs.items():
            original = json.loads(self.cases[base + "_repair_none"][0])
            for repair in ("missing", "domain", "binding"):
                with self.subTest(case=base, repair=repair):
                    changed = copy.deepcopy(original)
                    if repair == "missing":
                        index, row = next(
                            (index, row)
                            for index, row in enumerate(self.complete["records"])
                            if (row["sensor_id"], row["kind"]) == (sensor, missing_kind)
                        )
                        changed["records"].insert(index, copy.deepcopy(row))
                    else:
                        row = next(
                            row
                            for row in changed["records"]
                            if row["sensor_id"] != sensor and row["kind"] == bad_kind
                        )
                        if repair == "domain":
                            row["clock_domain"] = changed["capture"]["clock_domain"]
                        else:
                            row["rig_sha256"] = hashlib.sha256(
                                self.encode(changed["rig"])
                            ).hexdigest()
                    self.assertEqual(
                        self.encode(changed), self.cases[base + "_repair_" + repair][0]
                    )

    def test_dropping_any_one_finding_is_rejected(self):
        for name, (raw, report) in self.cases.items():
            for finding in report["findings"]:
                changed = copy.deepcopy(report)
                changed["findings"].remove(finding)
                for mode in ("report", "process"):
                    with self.subTest(case=name, omitted=finding, mode=mode):
                        with (
                            patch.object(
                                consumer, self.generate.__name__, return_value={name: (raw, report)}
                            ),
                            patch.object(
                                consumer,
                                "validate",
                                return_value=changed if mode == "report" else report,
                            ) as validate,
                            patch.object(
                                consumer.subprocess, "run", return_value=self.result(changed)
                            ) as run,
                        ):
                            with self.assertRaisesRegex(
                                AssertionError,
                                "^" + self.diagnostic + mode + "_mismatch:" + name + "$",
                            ):
                                self.check(self.case)
                        validate.assert_called_once_with(raw, now_ms=1050)
                        if mode == "report":
                            run.assert_not_called()
                        else:
                            self.assert_process_call(run, raw)


class DeclarationWrongCaseReferenceTests(unittest.TestCase):
    encode = DeclarationCollectionBoundaryTests.encode
    assert_process_call = DeclarationCollectionBoundaryTests.assert_process_call

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        self.original = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        self.cases = {}
        for index, token in enumerate(("THERMAL",) * 3 + ("DEPTH",) * 3):
            doc = copy.deepcopy(self.original)
            doc["records"][index]["sensor_id"] = token
            self.cases[f"sensor_{index}"] = self.encode(doc)
        self.good = SimpleNamespace(
            returncode=2,
            stdout=b"",
            stderr=("invalid_qualification_manifest" + os.linesep).encode("ascii"),
        )

    def test_independent_documents_rejection_and_single_reference_repairs(self):
        original = copy.deepcopy(self.case)
        self.assertEqual(consumer.declaration_wrong_case_references(self.case), self.cases)
        with patch.object(consumer.subprocess, "run", return_value=self.good) as run:
            self.assertEqual(consumer.check_declaration_wrong_case_references(self.case), 6)
        self.assertEqual(run.call_count, 6)
        for call, (name, raw) in zip(run.call_args_list, self.cases.items()):
            self.assertEqual(
                call.args[0],
                [consumer.sys.executable, "-I", "-m", "qualification", "--now-ms", "1050"],
            )
            self.assertEqual(
                call.kwargs,
                {"input": raw, "capture_output": True, "check": False, "timeout": 10},
            )
            doc = json.loads(raw)
            index = int(name[-1])
            doc["records"][index]["sensor_id"] = self.original["records"][index]["sensor_id"]
            self.assertEqual(doc, self.original)
            repaired = self.encode(doc)
            expected = copy.deepcopy(
                self.case["expected_report"]["captures"][0]["report"]["declaration"]
            )
            expected["input_sha256"] = hashlib.sha256(repaired).hexdigest()
            self.assertEqual(
                self.encode(consumer.validate(repaired, now_ms=1050)), self.encode(expected)
            )
        self.assertEqual(self.case, original)

    def test_every_case_requires_the_fixed_library_error(self):
        for name, raw in self.cases.items():
            for error in (None, ValueError("PRIVATE wrong reference")):
                with self.subTest(case=name, error=error):
                    with (
                        patch.object(
                            consumer, "declaration_wrong_case_references", return_value={name: raw}
                        ),
                        patch.object(
                            consumer, "validate", side_effect=error, return_value={}
                        ) as validate,
                        patch.object(consumer.subprocess, "run") as run,
                    ):
                        suffix = "missing" if error is None else "mismatch"
                        with self.assertRaisesRegex(
                            AssertionError,
                            "^declaration_case_reference_error_" + suffix + ":" + name + "$",
                        ):
                            consumer.check_declaration_wrong_case_references(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    run.assert_not_called()

    def test_every_case_checks_status_bytes_and_diagnostic(self):
        for name, raw in self.cases.items():
            for key, value in (
                ("returncode", 0),
                ("returncode", 1),
                ("stdout", b"PRIVATE"),
                ("stdout", b"{}"),
                ("stderr", b""),
                ("stderr", self.good.stderr + b"PRIVATE"),
                ("stderr", b"different_error" + os.linesep.encode("ascii")),
            ):
                with self.subTest(case=name, key=key, value=value):
                    result = copy.copy(self.good)
                    setattr(result, key, value)
                    with (
                        patch.object(
                            consumer, "declaration_wrong_case_references", return_value={name: raw}
                        ),
                        patch.object(consumer, "validate", wraps=consumer.validate) as validate,
                        patch.object(consumer.subprocess, "run", return_value=result) as run,
                    ):
                        with self.assertRaisesRegex(
                            AssertionError, "^declaration_wrong_case_process_mismatch:" + name + "$"
                        ):
                            consumer.check_declaration_wrong_case_references(self.case)
                    validate.assert_called_once_with(raw, now_ms=1050)
                    self.assert_process_call(run, raw)


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


class DeclarationClockIsolationTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_clock_isolation)
    check = staticmethod(consumer.check_declaration_clock_isolation)
    diagnostic = "declaration_clock_isolation_"
    count = 72

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        original = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        original["rig"]["sensors"].append(
            dict(original["rig"]["sensors"][0], id="radar", kind="radar")
        )
        digest = hashlib.sha256(self.encode(original["rig"])).hexdigest()
        original["records"] += [
            dict(copy.deepcopy(row), sensor_id="radar") for row in original["records"][:3]
        ]
        for row in original["records"]:
            row["rig_sha256"] = digest
        self.cases = {}
        # Literal findings for every repair/boundary; neither generator nor
        # validator computes this oracle. Enumerate all six clock orders.
        for bound, uncertainty in ((50, 1), (51, 2)):
            for family, third, repaired_findings in (
                ("neutral", (0, 0), [] if bound == 50 else ["clock_pair_skew"]),
                ("pair", (0, 50), ["clock_pair_skew"]),
                ("reference", (100, 1), ["clock_pair_skew", "clock_reference_skew"]),
            ):
                for order in ("012", "021", "102", "120", "201", "210"):
                    for domain in ("foreign", "repaired"):
                        doc = copy.deepcopy(original)
                        for slot, offset, error in ((1, -24, 1), (4, 24, uncertainty), (7, *third)):
                            doc["records"][slot]["data"] = {
                                "at_ms": 1050,
                                "offset_ms": offset,
                                "uncertainty_ms": error,
                            }
                        if domain == "foreign":
                            doc["records"][7]["clock_domain"] = "foreign_clock"
                        clocks = [doc["records"][1], doc["records"][4], doc["records"][7]]
                        for slot, index in zip((1, 4, 7), order):
                            doc["records"][slot] = clocks[int(index)]
                        findings = (
                            repaired_findings
                            if domain == "repaired"
                            else (
                                ["clock_domain_mismatch"]
                                if bound == 50
                                else ["clock_domain_mismatch", "clock_pair_skew"]
                            )
                        )
                        self.save(f"{family}_{bound}_{order}_{domain}", doc, 3, 9, findings)

    def test_single_domain_repairs_and_record_permutation_invariance(self):
        for name, (raw, report) in self.cases.items():
            family, bound, order, domain = name.split("_")
            with self.subTest(case=name):
                baseline_raw, baseline_report = self.cases[f"{family}_{bound}_012_{domain}"]
                self.assertEqual(
                    dict(report, input_sha256=None), dict(baseline_report, input_sha256=None)
                )
                doc, baseline = json.loads(raw), json.loads(baseline_raw)
                self.assertEqual(
                    sorted(doc["records"], key=lambda row: (row["sensor_id"], row["kind"])),
                    sorted(baseline["records"], key=lambda row: (row["sensor_id"], row["kind"])),
                )
                if domain == "foreign":
                    clock = next(
                        row
                        for row in doc["records"]
                        if (row["sensor_id"], row["kind"]) == ("radar", "clock")
                    )
                    clock["clock_domain"] = doc["capture"]["clock_domain"]
                    self.assertEqual(
                        self.encode(doc), self.cases[f"{family}_{bound}_{order}_repaired"][0]
                    )

    def test_each_skew_and_domain_finding_is_required(self):
        for name, (raw, report) in self.cases.items():
            for finding in report["findings"]:
                changed = copy.deepcopy(report)
                changed["findings"].remove(finding)
                for mode in ("report", "process"):
                    with self.subTest(case=name, omitted=finding, mode=mode):
                        with (
                            patch.object(
                                consumer, self.generate.__name__, return_value={name: (raw, report)}
                            ),
                            patch.object(
                                consumer,
                                "validate",
                                return_value=changed if mode == "report" else report,
                            ) as validate,
                            patch.object(
                                consumer.subprocess, "run", return_value=self.result(changed)
                            ) as run,
                        ):
                            with self.assertRaisesRegex(
                                AssertionError,
                                "^" + self.diagnostic + mode + "_mismatch:" + name + "$",
                            ):
                                self.check(self.case)
                        validate.assert_called_once_with(raw, now_ms=1050)
                        if mode == "report":
                            run.assert_not_called()
                        else:
                            self.assert_process_call(run, raw)


class DeclarationNumericBoundaryTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_numeric_boundaries)
    check = staticmethod(consumer.check_declaration_numeric_boundaries)
    diagnostic = "declaration_numeric_"
    count = 28

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        original = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        self.cases = {}
        maximum = 2**53 - 1000
        # Pin record positions and complete data objects independently of the
        # generator's field traversal. Equal calibration ends isolate admission
        # of the maximum valid_from instant from reversed-interval rejection.
        for base in (0, 3):
            for offset, name, data, findings in (
                (0, "zero", {"valid_from_ms": 0, "valid_until_ms": 0}, ["calibration_interval"]),
                (
                    0,
                    "maximum",
                    {"valid_from_ms": maximum, "valid_until_ms": maximum},
                    ["calibration_interval"],
                ),
                (0, "full_range", {"valid_from_ms": 0, "valid_until_ms": maximum}, []),
                (
                    1,
                    "at_zero",
                    {"at_ms": 0, "offset_ms": 0, "uncertainty_ms": 1},
                    ["record_outside_capture", "record_stale"],
                ),
                (
                    1,
                    "at_maximum",
                    {"at_ms": maximum, "offset_ms": 0, "uncertainty_ms": 1},
                    ["record_outside_capture"],
                ),
                (
                    1,
                    "offset_minimum",
                    {"at_ms": 1050, "offset_ms": -maximum, "uncertainty_ms": 1},
                    ["clock_pair_skew", "clock_reference_skew"],
                ),
                (1, "offset_zero", {"at_ms": 1050, "offset_ms": 0, "uncertainty_ms": 1}, []),
                (
                    1,
                    "offset_maximum",
                    {"at_ms": 1050, "offset_ms": maximum, "uncertainty_ms": 1},
                    ["clock_pair_skew", "clock_reference_skew"],
                ),
                (1, "uncertainty_zero", {"at_ms": 1050, "offset_ms": 0, "uncertainty_ms": 0}, []),
                (
                    1,
                    "uncertainty_maximum",
                    {"at_ms": 1050, "offset_ms": 0, "uncertainty_ms": maximum},
                    ["clock_pair_skew", "clock_reference_skew"],
                ),
                (
                    2,
                    "at_zero",
                    {"at_ms": 0, "lighting": "zero_visible"},
                    ["record_outside_capture", "record_stale"],
                ),
                (
                    2,
                    "at_maximum",
                    {"at_ms": maximum, "lighting": "zero_visible"},
                    ["record_outside_capture"],
                ),
            ):
                doc = copy.deepcopy(original)
                doc["records"][base + offset]["data"] = data
                self.save(f"record_{base + offset}_{name}", doc, 2, 6, findings)
        for name, left, right, uncertainty, findings in (
            ("equal_minimum", -maximum, -maximum, 0, ["clock_reference_skew"]),
            ("equal_maximum", maximum, maximum, 0, ["clock_reference_skew"]),
            (
                "opposite_forward",
                -maximum,
                maximum,
                maximum,
                ["clock_pair_skew", "clock_reference_skew"],
            ),
            (
                "opposite_reverse",
                maximum,
                -maximum,
                maximum,
                ["clock_pair_skew", "clock_reference_skew"],
            ),
        ):
            doc = copy.deepcopy(original)
            for index, value in ((1, left), (4, right)):
                doc["records"][index]["data"] = {
                    "at_ms": 1050,
                    "offset_ms": value,
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


class DeclarationProvenanceTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_provenance_cases)
    check = staticmethod(consumer.check_declaration_provenance)
    diagnostic = "declaration_provenance_"
    count = 24

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        original = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        self.cases = {}
        # Literal counts and record positions independently pin provenance
        # accounting, including unequal mixed counts and negative findings.
        for profile, labels, counts in (
            ("synthetic", ["synthetic"] * 6, (6, 0, 0)),
            ("recorded", ["recorded"] * 6, (0, 6, 0)),
            ("external_unverified", ["external_unverified"] * 6, (0, 0, 6)),
            (
                "mixed",
                [
                    "synthetic",
                    "recorded",
                    "recorded",
                    "external_unverified",
                    "external_unverified",
                    "external_unverified",
                ],
                (1, 2, 3),
            ),
        ):
            for state, findings in (
                ("valid", []),
                ("invalid", ["calibration_interval", "rig_binding_mismatch"]),
            ):
                for order, indices in (
                    ("forward", (0, 1, 2, 3, 4, 5)),
                    ("reverse", (5, 4, 3, 2, 1, 0)),
                    ("interleaved", (0, 2, 4, 1, 3, 5)),
                ):
                    doc = copy.deepcopy(original)
                    for index in range(6):
                        doc["records"][index]["evidence"] = labels[index]
                    if state == "invalid":
                        self.assertEqual(doc["records"][0]["kind"], "calibration")
                        doc["records"][0]["data"]["valid_until_ms"] = 1049
                        doc["records"][0]["rig_sha256"] = "0" * 64
                    doc["records"] = [doc["records"][i] for i in indices]
                    name = profile + "_" + state + "_" + order
                    self.save(name, doc, 2, 6, findings)
                    self.cases[name][1]["evidence_counts"] = dict(
                        zip(("synthetic", "recorded", "external_unverified"), counts)
                    )

    def test_record_order_changes_only_the_byte_commitment(self):
        for profile in ("synthetic", "recorded", "external_unverified", "mixed"):
            for state in ("valid", "invalid"):
                reports, commitments = [], set()
                for order in ("forward", "reverse", "interleaved"):
                    raw, _ = self.cases[profile + "_" + state + "_" + order]
                    report = consumer.validate(raw, now_ms=1050)
                    commitments.add(report.pop("input_sha256"))
                    reports.append(report)
                self.assertEqual(len(commitments), 3)
                self.assertEqual(reports[0], reports[1])
                self.assertEqual(reports[0], reports[2])


class DeclarationRigBindingTests(DeclarationCollectionBoundaryTests):
    generate = staticmethod(consumer.declaration_rig_binding_cases)
    check = staticmethod(consumer.check_declaration_rig_bindings)
    diagnostic = "declaration_rig_binding_"
    count = 32

    def setUp(self):
        self.case = next(case for case in consumer.corpus(CORPUS) if case["id"] == "complete")
        original = json.loads(bytes.fromhex(self.case["captures"][0]["manifest_hex"]))
        self.cases = {}
        # Pin each mutation independently of the installed generator and never
        # derive expected findings from the implementation under test.
        changes = (
            ("id", ("id",), "changed-rig"),
            ("configuration_sha256", ("configuration_sha256",), "a" * 64),
            ("thermal_device_sha256", ("sensors", 0, "device_sha256"), "b" * 64),
            ("thermal_mount_sha256", ("sensors", 0, "mount_sha256"), "b" * 64),
            ("depth_device_sha256", ("sensors", 1, "device_sha256"), "b" * 64),
            ("depth_mount_sha256", ("sensors", 1, "mount_sha256"), "b" * 64),
            ("sensor_order", ("sensors",), original["rig"]["sensors"][::-1]),
        )
        for state, findings in (("valid", []), ("invalid", ["calibration_interval"])):
            baseline = copy.deepcopy(original)
            if state == "invalid":
                self.assertEqual(baseline["records"][0]["kind"], "calibration")
                baseline["records"][0]["data"]["valid_until_ms"] = 1049
            for name, path, value in changes:
                doc = copy.deepcopy(baseline)
                parent = doc["rig"]
                for key in path[:-1]:
                    parent = parent[key]
                self.assertNotEqual(parent[path[-1]], value)
                parent[path[-1]] = value
                prefix = state + "_" + name
                self.save(prefix + "_old", doc, 2, 6, findings + ["rig_binding_mismatch"])
                digest = hashlib.sha256(self.encode(doc["rig"])).hexdigest()
                for record in doc["records"]:
                    self.assertNotEqual(record["rig_sha256"], digest)
                    record["rig_sha256"] = digest
                self.save(prefix + "_repaired", doc, 2, 6, findings)
            self.save(state + "_members_forward", baseline, 2, 6, findings)
            ordered = json.loads(
                self.encode(baseline), object_pairs_hook=lambda pairs: dict(reversed(pairs))
            )
            raw = json.dumps(ordered, separators=(",", ":")).encode("ascii")
            report = copy.deepcopy(self.cases[state + "_members_forward"][1])
            report["input_sha256"] = hashlib.sha256(raw).hexdigest()
            self.cases[state + "_members_reverse"] = raw, report

    def test_every_record_requires_the_new_rig_commitment(self):
        for name, (raw, expected) in self.cases.items():
            if not name.endswith("_repaired"):
                continue
            old, _ = self.cases[name.removesuffix("_repaired") + "_old"]
            old_doc = json.loads(old)
            for index in range(6):
                with self.subTest(case=name, record=index):
                    doc = json.loads(raw)
                    doc["records"][index]["rig_sha256"] = old_doc["records"][index]["rig_sha256"]
                    partial = self.encode(doc)
                    report = copy.deepcopy(expected)
                    report.update(
                        input_sha256=hashlib.sha256(partial).hexdigest(),
                        declaration_checks_passed=False,
                        findings=expected["findings"] + ["rig_binding_mismatch"],
                    )
                    self.assertEqual(
                        self.encode(consumer.validate(partial, now_ms=1050)), self.encode(report)
                    )

    def test_member_order_preserves_rig_binding_but_changes_input_commitment(self):
        for state in ("valid", "invalid"):
            forward, expected = self.cases[state + "_members_forward"]
            reverse, reverse_expected = self.cases[state + "_members_reverse"]
            self.assertNotEqual(forward, reverse)
            self.assertEqual(json.loads(forward), json.loads(reverse))
            self.assertNotEqual(expected["input_sha256"], reverse_expected["input_sha256"])
            reports = [consumer.validate(raw, now_ms=1050) for raw in (forward, reverse)]
            for report in reports:
                report.pop("input_sha256")
            self.assertEqual(self.encode(reports[0]), self.encode(reports[1]))


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
        for name, args in consumer.invalid_declaration_arguments().items():
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
                    # Full traversal is checked above; isolate each failing case
                    # instead of replaying every successful prefix per corruption.
                    with (
                        patch.object(
                            consumer, "invalid_declaration_arguments", return_value={name: args}
                        ),
                        patch.object(consumer.subprocess, "run", return_value=bad) as run,
                    ):
                        with self.assertRaises(AssertionError) as error:
                            consumer.check_declaration_arguments(self.case)
                    self.assertEqual(
                        str(error.exception), "declaration_argument_process_mismatch:" + name
                    )
                    run.assert_called_once_with(
                        [consumer.sys.executable, "-I", "-m", "qualification", *args],
                        input=self.raw,
                        capture_output=True,
                        check=False,
                        timeout=10,
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
            self.assertEqual(consumer.check_declaration_malformed_inputs(self.case), 389)
        self.assertEqual(run.call_count, 389)
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
                if not name.startswith(
                    ("numeric_", "record_numeric_", "structure_", "value_", "collection_")
                )
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

    def test_record_numeric_cases_reject_one_scalar_and_repair_to_complete(self):
        original = json.loads(self.raw)
        cases = consumer.declaration_record_numeric_inputs(self.raw)
        expected_cases = {}
        maximum = 2**53 - 1000
        for base in (0, 3):
            for offset, key, valid, minimum in (
                (0, "valid_from_ms", 0, 0),
                (0, "valid_until_ms", 1100, 0),
                (1, "at_ms", 1050, 0),
                (1, "offset_ms", 0, -maximum),
                (1, "uncertainty_ms", 1, 0),
                (2, "at_ms", 1050, 0),
            ):
                for label, token in (
                    ("boolean", b"true"),
                    ("float", f"{valid}.0".encode()),
                    ("string", f'"{valid}"'.encode()),
                    ("null", b"null"),
                    ("array", b"[]"),
                    ("object", b"{}"),
                    ("below_minimum", str(minimum - 1).encode()),
                    ("above_maximum", str(maximum + 1).encode()),
                ):
                    name = f"record_numeric_{base + offset}_{key}_{label}"
                    with self.subTest(case=name):
                        doc = copy.deepcopy(original)
                        data = doc["records"][base + offset]["data"]
                        self.assertIs(type(data[key]), int)
                        self.assertEqual(data[key], valid)
                        data[key] = "NUMERIC_PLACEHOLDER"
                        encoded = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
                        raw = encoded.replace(b'"NUMERIC_PLACEHOLDER"', token, 1)
                        expected_cases[name] = raw
                        with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
                            consumer.validate(cases[name], now_ms=1050)
                        data[key] = valid
                        fixed = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
                        self.assertEqual(fixed, self.raw.rstrip())
                        report = copy.deepcopy(
                            self.case["expected_report"]["captures"][0]["report"]["declaration"]
                        )
                        report["input_sha256"] = hashlib.sha256(fixed).hexdigest()
                        self.assertEqual(
                            consumer.canonical(consumer.validate(fixed, now_ms=1050)),
                            consumer.canonical(report),
                        )
        self.assertEqual(cases, expected_cases)
        self.assertEqual(len(cases), 96)

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
        cases = consumer.declaration_malformed_inputs(self.raw)
        self.assertEqual(len(cases), 389)
        for name, raw in cases.items():
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
                    # Full traversal is checked separately; isolate this outcome
                    # without rebuilding the corpus or replaying earlier cases.
                    with (
                        patch.object(
                            consumer, "declaration_malformed_inputs", return_value={name: raw}
                        ) as inputs,
                        patch.object(consumer.subprocess, "run", return_value=bad) as run,
                    ):
                        with self.assertRaises(AssertionError) as error:
                            consumer.check_declaration_malformed_inputs(self.case)
                    inputs.assert_called_once_with(self.raw)
                    run.assert_called_once_with(
                        [consumer.sys.executable, "-I", "-m", "qualification", "--now-ms", "1050"],
                        input=raw,
                        capture_output=True,
                        check=False,
                        timeout=10,
                    )
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
        for name, original in self.reports.items():
            args = self.boundaries[name]
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
                    with (
                        patch.object(
                            consumer, "aggregate_artifact_arguments", return_value={name: args}
                        ),
                        patch.object(consumer, "evaluate", return_value=report) as evaluate,
                        patch.object(consumer.subprocess, "run") as run,
                    ):
                        with self.assertRaisesRegex(
                            AssertionError, "^aggregate_assessment_" + error + ":" + name + "$"
                        ):
                            consumer.check_aggregate_artifacts(self.case)
                    evaluate.assert_called_once_with(*args)
                    run.assert_not_called()

    def test_process_cannot_reject_exact_limit_hide_findings_or_change_status(self):
        from qualification.tests.test_assessment_cli import frame

        for name, report in self.reports.items():
            args = self.boundaries[name]
            raw = frame(args)
            good = self.result(report)
            for status, stdout, stderr in (
                (0, good.stdout, b""),
                (2, b"", b"invalid_qualification_assessment" + os.linesep.encode("ascii")),
                (1, b"{}" + os.linesep.encode("ascii"), b""),
                (1, good.stdout + b"PRIVATE", b""),
                (1, good.stdout, b"PRIVATE"),
            ):
                with self.subTest(case=name, status=status, stderr=stderr):
                    bad = SimpleNamespace(returncode=status, stdout=stdout, stderr=stderr)
                    with (
                        patch.object(
                            consumer, "aggregate_artifact_arguments", return_value={name: args}
                        ),
                        patch.object(consumer, "evaluate", wraps=consumer.evaluate) as evaluate,
                        patch.object(consumer.subprocess, "run", return_value=bad) as run,
                    ):
                        with self.assertRaisesRegex(
                            AssertionError, "^aggregate_assessment_process_mismatch:" + name + "$"
                        ):
                            consumer.check_aggregate_artifacts(self.case)
                    evaluate.assert_called_once_with(*args)
                    run.assert_called_once_with(
                        [consumer.sys.executable, "-I", "-m", "qualification.assessment_cli"],
                        input=raw,
                        capture_output=True,
                        check=False,
                        timeout=10,
                    )


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
            for name, args in consumer.unexpected_arguments().items():
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
                        # Full traversal is checked above; isolate each failing case
                        # instead of replaying every successful prefix per corruption.
                        with (
                            patch.object(
                                consumer, "unexpected_arguments", return_value={name: args}
                            ),
                            patch.object(consumer.subprocess, "run", return_value=bad) as run,
                        ):
                            with self.assertRaises(AssertionError) as error:
                                consumer.check_unexpected_arguments(
                                    module.__name__, raw, diagnostic
                                )
                        self.assertEqual(
                            str(error.exception),
                            "argument_process_mismatch:" + module.__name__ + ":" + name,
                        )
                        run.assert_called_once_with(
                            [consumer.sys.executable, "-I", "-m", module.__name__, *args],
                            input=raw,
                            capture_output=True,
                            check=False,
                            timeout=10,
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
            for name, raw in cases.items():
                args = [] if arguments is None else arguments[name]
                selected_arguments = None if arguments is None else {name: args}
                command = [consumer.sys.executable, "-I", "-m", module.__name__, *args]
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
                            # Full traversal is checked above. Only the same input's
                            # stdout-only success must precede a both-pipes failure.
                            results = [bad]
                            if close_errors:
                                results.insert(
                                    0, SimpleNamespace(returncode=2, stdout=None, stderr=fixed)
                                )
                            with patch.object(
                                consumer.subprocess, "run", side_effect=results
                            ) as run:
                                with self.assertRaises(AssertionError) as error:
                                    consumer.check_closed_pipes(
                                        module.__name__,
                                        {name: raw},
                                        diagnostic,
                                        case_arguments=selected_arguments,
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
                            self.assertEqual(run.call_count, 2 if close_errors else 1)
                            for index, call in enumerate(run.call_args_list):
                                output = call.kwargs["stdout"]
                                error_stream = call.kwargs["stderr"]
                                self.assertEqual(call.args, (command,))
                                self.assertEqual(
                                    call.kwargs,
                                    {
                                        "input": raw,
                                        "stdout": output,
                                        "stderr": error_stream,
                                        "check": False,
                                        "timeout": 10,
                                    },
                                )
                                self.assertEqual(output.mode, "wb")
                                self.assertTrue(output.closed)
                                if index == 0:
                                    self.assertEqual(error_stream, consumer.subprocess.PIPE)
                                else:
                                    self.assertIsNot(error_stream, output)
                                    self.assertEqual(error_stream.mode, "wb")
                                    self.assertTrue(error_stream.closed)

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
        for module, cases, diagnostic, count in self.cases():
            self.assertEqual(len(cases), count)
            fixed = (diagnostic + os.linesep).encode("ascii")
            for name, raw in cases.items():
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
                        with patch.object(consumer.subprocess, "run", return_value=bad) as run:
                            with self.assertRaises(AssertionError) as error:
                                consumer.check_malformed_frames(module, {name: raw}, diagnostic)
                        self.assertEqual(
                            str(error.exception),
                            "malformed_process_mismatch:" + module + ":" + name,
                        )
                        run.assert_called_once_with(
                            [consumer.sys.executable, "-I", "-m", module],
                            input=raw,
                            capture_output=True,
                            check=False,
                            timeout=10,
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
