"""Synthetic declaration behavior; no instrument or physical evidence."""

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


def encoded(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


def fixture():
    rig = {
        "id": "synthetic-rig",
        "configuration_sha256": "1" * 64,
        "sensors": [
            {"id": "thermal", "kind": "lwir", "device_sha256": "2" * 64, "mount_sha256": "3" * 64},
            {"id": "depth", "kind": "depth", "device_sha256": "4" * 64, "mount_sha256": "5" * 64},
        ],
    }
    records = []
    for sensor in rig["sensors"]:
        for kind, data in (
            ("calibration", {"valid_from_ms": 0, "valid_until_ms": 1100}),
            ("clock", {"at_ms": 1050, "offset_ms": 0, "uncertainty_ms": 1}),
            ("environment", {"at_ms": 1050, "lighting": "zero_visible"}),
        ):
            records.append(
                {
                    "sensor_id": sensor["id"],
                    "kind": kind,
                    "evidence": "synthetic",
                    "artifact_sha256": "6" * 64,
                    "rig_sha256": hashlib.sha256(encoded(rig)).hexdigest(),
                    "clock_domain": "synthetic-boot",
                    "data": data,
                }
            )
    return {
        "version": 1,
        "rig": rig,
        "capture": {"clock_domain": "synthetic-boot", "start_ms": 1000, "end_ms": 1050},
        "records": records,
    }


class EvidenceTests(unittest.TestCase):
    def validate(self, doc, now_ms=1050):
        # A missing implementation is an explicit feature failure during RED.
        self.assertIsNotNone(importlib.util.find_spec("qualification.evidence"))
        from qualification.evidence import validate

        return validate(doc if type(doc) is bytes else encoded(doc), now_ms=now_ms)

    def rejected(self, doc, now_ms=1050):
        with self.assertRaisesRegex(ValueError, "^invalid_qualification_manifest$"):
            self.validate(doc, now_ms)

    def test_synthetic_pass_never_qualifies_hardware_or_verifies_artifacts(self):
        doc = fixture()
        report = self.validate(doc)
        self.assertEqual(
            report,
            {
                "version": 1,
                "input_sha256": hashlib.sha256(encoded(doc)).hexdigest(),
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
        self.assertEqual(report, self.validate(encoded(doc)))

    def test_external_declarations_cannot_self_certify(self):
        doc = fixture()
        for record in doc["records"]:
            record["evidence"] = "external_unverified"
        report = self.validate(doc)
        self.assertFalse(report["physical_qualification_passed"])
        self.assertFalse(report["artifacts_verified"])
        self.assertEqual(report["evidence_counts"]["external_unverified"], 6)
        doc["physical_qualification_passed"] = True
        self.rejected(doc)

    def test_missing_evidence_is_retained_without_echoing_identifiers(self):
        doc = fixture()
        doc["records"] = []
        report = self.validate(doc)
        self.assertFalse(report["declaration_checks_passed"])
        self.assertEqual(
            report["findings"], ["missing_calibration", "missing_clock", "missing_environment"]
        )
        self.assertNotIn("synthetic-rig", json.dumps(report))
        self.assertNotIn("thermal", json.dumps(report))

    def test_capture_age_inclusive_and_future(self):
        self.assertTrue(self.validate(fixture(), 1150)["declaration_checks_passed"])
        self.assertEqual(self.validate(fixture(), 1151)["findings"], ["capture_stale"])
        self.assertEqual(self.validate(fixture(), 1049)["findings"], ["capture_future"])

    def test_calibration_requires_entire_capture_interval(self):
        for key, value in (("valid_from_ms", 1001), ("valid_until_ms", 1049)):
            doc = fixture()
            doc["records"][0]["data"][key] = value
            self.assertEqual(self.validate(doc)["findings"], ["calibration_interval"])

    def test_binding_and_clock_domain_mismatch_retained(self):
        doc = fixture()
        doc["records"][0]["rig_sha256"] = "0" * 64
        doc["records"][1]["clock_domain"] = "different-boot"
        self.assertEqual(
            self.validate(doc)["findings"], ["clock_domain_mismatch", "rig_binding_mismatch"]
        )

    def test_record_time_bounds(self):
        for index in (1, 2):
            for at_ms, expected in (
                (1051, "record_outside_capture"),
                (999, "record_outside_capture"),
            ):
                doc = fixture()
                doc["records"][index]["data"]["at_ms"] = at_ms
                self.assertIn(expected, self.validate(doc)["findings"])
            doc = fixture()
            doc["capture"]["start_ms"] = 900
            doc["records"][index]["data"]["at_ms"] = 950
            self.assertTrue(self.validate(doc)["declaration_checks_passed"])
            doc["records"][index]["data"]["at_ms"] = 949
            self.assertEqual(self.validate(doc)["findings"], ["record_stale"])

    def test_pairwise_uncertainty_cannot_hide_behind_individual_clock_bounds(self):
        doc = fixture()
        doc["records"][1]["data"].update(offset_ms=-24, uncertainty_ms=1)
        doc["records"][4]["data"].update(offset_ms=24, uncertainty_ms=1)
        self.assertTrue(self.validate(doc)["declaration_checks_passed"])
        doc["records"][4]["data"]["uncertainty_ms"] = 2
        self.assertEqual(self.validate(doc)["findings"], ["clock_pair_skew"])
        doc["records"][1]["data"].update(offset_ms=0, uncertainty_ms=51)
        self.assertIn("clock_reference_skew", self.validate(doc)["findings"])

    def test_duplicate_and_unknown_fields_rejected_at_all_levels(self):
        original = fixture()
        for selector in (
            lambda d: d,
            lambda d: d["rig"],
            lambda d: d["rig"]["sensors"][0],
            lambda d: d["capture"],
            lambda d: d["records"][0],
            lambda d: d["records"][0]["data"],
        ):
            doc = copy.deepcopy(original)
            selector(doc)["person_identity"] = "PRIVATE_MARKER"
            self.rejected(doc)
        for name, replacement in (
            (b'"version":1', b'"version":1,"version":1'),
            (b'"at_ms":1050', b'"at_ms":1050,"at_ms":1050'),
        ):
            self.rejected(encoded(original).replace(name, replacement, 1))

    def test_strict_numeric_and_json_bounds(self):
        for value in (True, -1, 1.5, "1050", 2**53, None):
            self.rejected(fixture(), value)
            doc = fixture()
            doc["capture"]["end_ms"] = value
            self.rejected(doc)
        for bad in (b"NaN", b"Infinity", b"1e999", b"true", b"1.0"):
            self.rejected(
                encoded(fixture()).replace(b'"uncertainty_ms":1', b'"uncertainty_ms":' + bad)
            )
        for raw in (b"{}" + b" " * 65535, b"[" * 9 + b"0" + b"]" * 9, b"\xff", b"null", b"{"):
            self.rejected(raw)
        payload = encoded(fixture())
        self.assertTrue(
            self.validate(payload + b" " * (65536 - len(payload)))["declaration_checks_passed"]
        )

    def test_duplicate_sensor_record_invalid_types_and_hashes(self):
        mutations = (
            lambda d: d["rig"]["sensors"].append(d["rig"]["sensors"][0]),
            lambda d: d["records"].append(d["records"][0]),
            lambda d: d["records"][0].update(sensor_id="unknown"),
            lambda d: d["records"][0].update(artifact_sha256="A" * 64),
            lambda d: d["records"][0].update(evidence="hardware_passed"),
            lambda d: d["records"][0].update(kind=[]),
            lambda d: d["records"][0].update(data=None),
            lambda d: d.update(version=True),
            lambda d: d["capture"].update(start_ms=1051),
            lambda d: d["records"][0]["data"].update(valid_from_ms=1101),
        )
        for mutation in mutations:
            doc = fixture()
            mutation(doc)
            self.rejected(doc)

    def test_wrong_scalar_types_at_every_leaf_fail_closed(self):
        # Concrete malformed cases, not an unbounded fuzz campaign.
        original = fixture()

        def leaves(value, path=()):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield from leaves(child, path + (key,))
            elif isinstance(value, list):
                for key, child in enumerate(value):
                    yield from leaves(child, path + (key,))
            else:
                yield path

        for path in leaves(original):
            for wrong in (None, True, [], {}):
                with self.subTest(path=path, wrong=wrong):
                    doc = copy.deepcopy(original)
                    parent = doc
                    for key in path[:-1]:
                        parent = parent[key]
                    parent[path[-1]] = wrong
                    self.rejected(doc)


class CliTests(unittest.TestCase):
    def run_cli(self, payload):
        return subprocess.run(
            [sys.executable, "-m", "qualification", "--now-ms", "1050"],
            input=payload,
            capture_output=True,
            timeout=10,
            cwd=Path(__file__).resolve().parents[2],
            check=False,
        )

    def test_cli_report_and_fixed_failure(self):
        result = self.run_cli(encoded(fixture()))
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertFalse(json.loads(result.stdout)["physical_qualification_passed"])
        self.assertEqual(result.stdout, self.run_cli(encoded(fixture())).stdout)
        doc = fixture()
        doc["records"] = []
        result = self.run_cli(encoded(doc))
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["declaration_checks_passed"])
        for payload in (b'{"PRIVATE_MARKER":', b" " * 65537):
            result = self.run_cli(payload)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            self.assertEqual(result.stderr, b"invalid_qualification_manifest\n")

    def test_invalid_cli_argument_does_not_echo_private_input(self):
        result = subprocess.run(
            [sys.executable, "-m", "qualification", "--now-ms", "PRIVATE_MARKER"],
            input=b"",
            capture_output=True,
            timeout=10,
            cwd=Path(__file__).resolve().parents[2],
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"invalid_qualification_manifest\n")


if __name__ == "__main__":
    unittest.main()
