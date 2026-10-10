"""Replay tracked synthetic vectors without importing Python fixture builders."""

import hashlib
import json
import unittest
from pathlib import Path

from qualification.artifacts import verify
from qualification.campaign_bundle import evaluate

CORPUS = Path(__file__).resolve().parents[1] / "fixtures/consumer-vectors-v1.json"
CASE_IDS = {
    "complete",
    "stale",
    "altered_artifact",
    "wrong_references",
    "expired_and_altered",
    "reused_capture",
}


class ConsumerVectorTests(unittest.TestCase):
    def corpus(self):
        self.assertTrue(CORPUS.is_file(), "portable consumer corpus missing")
        with CORPUS.open("rb") as stream:
            raw = stream.read(32769)
        self.assertLessEqual(len(raw), 32768)
        corpus = json.loads(raw)
        self.assertEqual(set(corpus), {"version", "plan_utf8", "manifests_utf8", "cases"})
        self.assertIs(type(corpus["version"]), int)
        self.assertEqual(corpus["version"], 1)
        self.assertEqual(len(corpus["cases"]), len(CASE_IDS))
        self.assertEqual({case["id"] for case in corpus["cases"]}, CASE_IDS)
        for case in corpus["cases"]:
            self.assertEqual(
                set(case),
                {"id", "captures", "domain_hex", "procedure_hex", "artifacts_hex", "expected"},
            )
            self.assertTrue(case["captures"])
            for row in case["captures"]:
                self.assertEqual(set(row), {"case_id", "manifest_key", "now_ms"})
            self.assertEqual(set(case["expected"]), {"bundle", "artifacts"})
            self.assertEqual(
                set(case["expected"]["bundle"]),
                {
                    "coverage_findings",
                    "reference_findings",
                    "software_checks_passed",
                    "capture_counts",
                },
            )
            self.assertEqual(len(case["expected"]["artifacts"]), len(case["captures"]))
            for expected in case["expected"]["artifacts"]:
                self.assertEqual(
                    set(expected),
                    {
                        "declaration_findings",
                        "artifact_findings",
                        "software_checks_passed",
                        "artifact_bytes_verified",
                    },
                )
        return corpus

    def rows(self, corpus, case):
        return [
            {
                "case_id": row["case_id"],
                "manifest": corpus["manifests_utf8"][row["manifest_key"]].encode("utf-8"),
                "now_ms": row["now_ms"],
            }
            for row in case["captures"]
        ]

    def test_corpus_has_all_six_cases_and_exact_byte_inputs(self):
        corpus = self.corpus()
        self.assertEqual(set(corpus["manifests_utf8"]), {"complete", "expired"})
        for case in corpus["cases"]:
            with self.subTest(case=case["id"]):
                for row in self.rows(corpus, case):
                    self.assertEqual(set(row), {"case_id", "manifest", "now_ms"})
                    self.assertLessEqual(len(row["manifest"]), 65536)
                    self.assertIs(type(row["now_ms"]), int)
                for field in ("domain_hex", "procedure_hex"):
                    self.assertEqual(bytes.fromhex(case[field]).hex(), case[field])
                for digest, value in case["artifacts_hex"].items():
                    self.assertRegex(digest, r"^[0-9a-f]{64}$")
                    self.assertEqual(bytes.fromhex(value).hex(), value)

    def test_bundle_outcomes_match_portable_expectations(self):
        corpus = self.corpus()
        for case in corpus["cases"]:
            with self.subTest(case=case["id"]):
                plan = corpus["plan_utf8"].encode("utf-8")
                report = evaluate(
                    plan,
                    self.rows(corpus, case),
                    bytes.fromhex(case["domain_hex"]),
                    bytes.fromhex(case["procedure_hex"]),
                )
                expected = case["expected"]["bundle"]
                self.assertEqual(report["plan_sha256"], hashlib.sha256(plan).hexdigest())
                self.assertEqual(report["coverage"]["findings"], expected["coverage_findings"])
                self.assertEqual(
                    report["references"]["reference_findings"], expected["reference_findings"]
                )
                self.assertIs(report["software_checks_passed"], expected["software_checks_passed"])
                self.assertEqual(report["coverage"]["capture_counts"], expected["capture_counts"])
                for key in (
                    "artifact_bytes_verified",
                    "artifact_authenticity_verified",
                    "domain_verified",
                    "procedure_verified",
                    "physical_qualification_passed",
                ):
                    self.assertIs(report[key], False)

    def test_artifact_outcomes_match_portable_expectations(self):
        corpus = self.corpus()
        for case in corpus["cases"]:
            with self.subTest(case=case["id"]):
                supplied = {
                    key: bytes.fromhex(value) for key, value in case["artifacts_hex"].items()
                }
                for row, expected in zip(self.rows(corpus, case), case["expected"]["artifacts"]):
                    report = verify(row["manifest"], supplied, now_ms=row["now_ms"])
                    self.assertEqual(
                        report["declaration"]["input_sha256"],
                        hashlib.sha256(row["manifest"]).hexdigest(),
                    )
                    self.assertEqual(
                        report["declaration"]["findings"], expected["declaration_findings"]
                    )
                    self.assertEqual(report["artifact_findings"], expected["artifact_findings"])
                    for key in ("software_checks_passed", "artifact_bytes_verified"):
                        self.assertIs(report[key], expected[key])
                    self.assertIs(report["artifact_authenticity_verified"], False)
                    self.assertIs(report["physical_qualification_passed"], False)


if __name__ == "__main__":
    unittest.main()
