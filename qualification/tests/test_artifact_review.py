"""Independent artifact association and negative-evidence review cases."""

import hashlib
import unittest

from qualification import artifacts
from qualification.tests.test_artifacts import ABC, EMPTY, declaration
from qualification.tests.test_evidence import encoded

DEF = "cb8379ac2098aa165029e3938a51da0bcecfc008fd6795f401178647f96c5b34"


class ArtifactReviewTests(unittest.TestCase):
    def test_swapped_contents_fail_each_declared_association(self):
        doc = declaration()
        doc["records"][1]["artifact_sha256"] = DEF
        raw = encoded(doc)
        good = artifacts.verify(raw, {ABC: b"abc", DEF: b"def"}, now_ms=1050)
        self.assertTrue(good["software_checks_passed"])
        bad = artifacts.verify(raw, {ABC: b"def", DEF: b"abc"}, now_ms=1050)
        self.assertEqual(bad["artifact_findings"], ["artifact_digest_mismatch"])
        self.assertEqual(bad["artifact_counts"]["matched"], 0)
        self.assertEqual(bad["artifact_counts"]["mismatched"], 2)
        self.assertFalse(bad["software_checks_passed"])
        self.assertIs(bad["artifact_authenticity_verified"], False)
        self.assertIs(bad["physical_qualification_passed"], False)

    def test_combined_failures_cannot_replace_declaration_negatives(self):
        doc = declaration()
        doc["records"][0]["data"]["valid_until_ms"] = 1049
        doc["records"][1]["artifact_sha256"] = DEF
        report = artifacts.verify(encoded(doc), {ABC: b"bad", EMPTY: b""}, now_ms=1050)
        self.assertEqual(report["declaration"]["findings"], ["calibration_interval"])
        self.assertEqual(
            report["artifact_findings"],
            ["artifact_digest_mismatch", "artifact_missing", "artifact_unreferenced"],
        )
        self.assertFalse(report["software_checks_passed"])
        self.assertIs(report["physical_qualification_passed"], False)

    def test_changed_supplied_mapping_requires_new_verification(self):
        supplied = {ABC: b"abc"}
        raw = encoded(declaration())
        before = artifacts.verify(raw, supplied, now_ms=1050)
        supplied[ABC] = b"changed"
        after = artifacts.verify(raw, supplied, now_ms=1050)
        self.assertTrue(before["artifact_bytes_verified"])
        self.assertFalse(after["artifact_bytes_verified"])
        self.assertEqual(after["artifact_findings"], ["artifact_digest_mismatch"])
        self.assertEqual(
            before["declaration"]["input_sha256"], after["declaration"]["input_sha256"]
        )
        self.assertIs(before["artifact_authenticity_verified"], False)

    def test_full_aggregate_budget_matches_four_distinct_contents(self):
        payloads = [bytes([i]) * 1048576 for i in range(4)]
        digests = [hashlib.sha256(value).hexdigest() for value in payloads]
        doc = declaration()
        for i, row in enumerate(doc["records"]):
            row["artifact_sha256"] = digests[i % 4]
        report = artifacts.verify(encoded(doc), dict(zip(digests, payloads)), now_ms=1050)
        self.assertEqual(
            report["artifact_counts"],
            {
                "referenced": 4,
                "supplied": 4,
                "matched": 4,
                "missing": 0,
                "mismatched": 0,
                "unreferenced": 0,
                "supplied_bytes": 4194304,
            },
        )
        self.assertTrue(report["software_checks_passed"])
        self.assertIs(report["physical_qualification_passed"], False)
        over_budget = dict(zip(digests, payloads))
        over_budget[EMPTY] = b"x"
        with self.assertRaisesRegex(ValueError, "^invalid_qualification_artifacts$"):
            artifacts.verify(encoded(doc), over_budget, now_ms=1050)
