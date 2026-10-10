"""Replay pinned raw-byte assessment vectors without Python fixture builders."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qualification.assessment import evaluate

CORPUS = Path(__file__).resolve().parents[1] / "fixtures/assessment-vectors-v1.json"
CORPUS_SHA256 = "afe52af644bbc67dc0bdb0df3d13839ab1a3c3d768471ce32b02d314d899fa2c"
CASE_IDS = {
    "complete",
    "stale",
    "domain_unknown",
    "method_unknown",
    "artifact_missing",
    "simultaneous",
    "reused",
    "malformed_capture",
    "invalid_plan",
    "invalid_instant",
}


class AssessmentVectorTests(unittest.TestCase):
    def corpus(self):
        self.assertTrue(CORPUS.is_file(), "portable assessment corpus missing")
        with CORPUS.open("rb") as stream:
            raw = stream.read(262145)
        self.assertLessEqual(len(raw), 262144)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), CORPUS_SHA256)
        data = json.loads(raw)
        self.assertEqual(set(data), {"version", "cases"})
        self.assertIs(type(data["version"]), int)
        self.assertEqual(data["version"], 1)
        self.assertEqual(len(data["cases"]), len(CASE_IDS))
        self.assertEqual({case["id"] for case in data["cases"]}, CASE_IDS)
        return data["cases"]

    def raw(self, value):
        self.assertIs(type(value), str)
        result = bytes.fromhex(value)
        self.assertEqual(result.hex(), value)
        return result

    def arguments(self, case):
        self.assertEqual(
            set(case),
            {
                "id",
                "plan_hex",
                "domain_hex",
                "procedure_hex",
                "methods_hex",
                "captures",
                "expected_report",
                "expected_error",
            },
        )
        rows = []
        for row in case["captures"]:
            self.assertEqual(set(row), {"case_id", "manifest_hex", "now_ms", "artifacts_hex"})
            rows.append(
                {
                    "case_id": row["case_id"],
                    "manifest": self.raw(row["manifest_hex"]),
                    "now_ms": row["now_ms"],
                    "artifacts": {
                        key: self.raw(value) for key, value in row["artifacts_hex"].items()
                    },
                }
            )
        return (
            self.raw(case["plan_hex"]),
            rows,
            self.raw(case["domain_hex"]),
            self.raw(case["procedure_hex"]),
            {key: self.raw(value) for key, value in case["methods_hex"].items()},
        )

    def exact(self, actual, expected):
        self.assertIs(type(actual), type(expected))
        if type(expected) is dict:
            self.assertEqual(set(actual), set(expected))
            for key in expected:
                self.exact(actual[key], expected[key])
        elif type(expected) is list:
            self.assertEqual(len(actual), len(expected))
            for left, right in zip(actual, expected):
                self.exact(left, right)
        else:
            self.assertEqual(actual, expected)

    def test_complete_reports_and_fixed_errors_match(self):
        for case in self.corpus():
            with self.subTest(case=case["id"]):
                args = self.arguments(case)
                if case["expected_error"] is not None:
                    self.assertIsNone(case["expected_report"])
                    self.assertEqual(case["expected_error"], "invalid_qualification_assessment")
                    with self.assertRaisesRegex(ValueError, "^invalid_qualification_assessment$"):
                        evaluate(*args)
                else:
                    report = evaluate(*args)
                    self.exact(report, case["expected_report"])
                    self.assertIs(report["software_checks_passed"], case["id"] == "complete")
                    self.assertIs(report["physical_qualification_passed"], False)
                    self.assertIs(report["artifact_authenticity_verified"], False)

    def test_named_negatives_retain_their_independent_meaning(self):
        cases = {case["id"]: case for case in self.corpus()}
        reports = {
            key: evaluate(*self.arguments(value))
            for key, value in cases.items()
            if value["expected_error"] is None
        }
        self.assertIn("declaration_capture_stale", reports["stale"]["coverage"]["findings"])
        self.assertIn("domain_profile_unknown", reports["domain_unknown"]["domain"]["findings"])
        self.assertIn(
            "method_rule_unknown", reports["method_unknown"]["methods"]["method_findings"]
        )
        self.assertIn(
            "artifact_missing",
            reports["artifact_missing"]["captures"][0]["report"]["artifact_findings"],
        )
        self.assertIn("capture_reused", reports["reused"]["coverage"]["findings"])
        self.assertEqual(
            reports["malformed_capture"]["captures"][0]["findings"], ["capture_invalid"]
        )
        self.assertIsNone(reports["malformed_capture"]["captures"][0]["report"])
        combined = reports["simultaneous"]
        self.assertTrue(combined["coverage"]["findings"])
        self.assertTrue(combined["domain"]["findings"])
        self.assertTrue(combined["methods"]["method_findings"])
        self.assertTrue(combined["captures"][0]["report"]["artifact_findings"])
        self.assertTrue(reports["stale"]["artifact_bytes_verified"])
        self.assertEqual(
            {key for key, case in cases.items() if case["expected_error"] is not None},
            {"invalid_plan", "invalid_instant"},
        )

    def test_comparison_rejects_numeric_type_substitution(self):
        for wrong in (True, 1.0):
            for actual, expected in ((wrong, 1), (1, wrong)):
                with self.assertRaises(AssertionError):
                    self.exact({"nested": [actual]}, {"nested": [expected]})

    def test_corpus_pin_rejects_replacement_before_evaluation(self):
        original = CORPUS.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.json"
            for raw in (b'{"version":1,"cases":[]}', original + b" ", b" " * 262145):
                path.write_bytes(raw)
                with patch(__name__ + ".CORPUS", path):
                    with self.assertRaises(AssertionError):
                        self.corpus()


if __name__ == "__main__":
    unittest.main()
