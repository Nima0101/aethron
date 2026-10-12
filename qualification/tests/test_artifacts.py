"""Byte binding is distinct from instrument authenticity and qualification."""

import hashlib
import importlib.util
import json
import unittest

from qualification.tests.test_evidence import encoded, fixture

ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def declaration(digest=ABC):
    doc = fixture()
    for row in doc["records"]:
        row["artifact_sha256"] = digest
    return doc


class ArtifactTests(unittest.TestCase):
    def verify(self, doc, artifacts, now_ms=1050):
        self.assertIsNotNone(importlib.util.find_spec("qualification.artifacts"))
        from qualification.artifacts import verify

        return verify(doc if type(doc) is bytes else encoded(doc), artifacts, now_ms=now_ms)

    def test_known_bytes_match_without_authenticity_or_physical_claim(self):
        doc = declaration()
        supplied = {ABC: b"abc"}
        report = self.verify(doc, supplied)
        self.assertTrue(report["artifact_bytes_verified"])
        self.assertTrue(report["software_checks_passed"])
        self.assertFalse(report["artifact_authenticity_verified"])
        self.assertFalse(report["physical_qualification_passed"])
        self.assertFalse(report["declaration"]["artifacts_verified"])
        self.assertEqual(report["artifact_findings"], [])
        self.assertEqual(
            report["artifact_counts"],
            {
                "referenced": 1,
                "supplied": 1,
                "matched": 1,
                "missing": 0,
                "mismatched": 0,
                "unreferenced": 0,
                "supplied_bytes": 3,
            },
        )
        self.assertEqual(supplied, {ABC: b"abc"})
        self.assertEqual(doc, declaration())
        self.assertEqual(report, self.verify(doc, supplied))

    def test_absence_tampering_and_extra_payloads_are_retained(self):
        doc = declaration()
        doc["records"][1]["artifact_sha256"] = "0" * 64
        report = self.verify(doc, {ABC: b"PRIVATE_ARTIFACT_PAYLOAD", EMPTY: b""})
        self.assertFalse(report["artifact_bytes_verified"])
        self.assertFalse(report["software_checks_passed"])
        self.assertEqual(
            report["artifact_findings"],
            [
                "artifact_digest_mismatch",
                "artifact_missing",
                "artifact_unreferenced",
            ],
        )
        self.assertEqual(
            report["artifact_counts"],
            {
                "referenced": 2,
                "supplied": 2,
                "matched": 0,
                "missing": 1,
                "mismatched": 1,
                "unreferenced": 1,
                "supplied_bytes": 24,
            },
        )
        for private in ("PRIVATE_ARTIFACT_PAYLOAD", "synthetic-rig", ABC, EMPTY):
            self.assertNotIn(private, json.dumps(report))

    def test_calibration_failure_survives_matched_artifacts(self):
        doc = declaration()
        doc["records"][0]["data"]["valid_until_ms"] = 1049
        report = self.verify(doc, {ABC: b"abc"})
        self.assertTrue(report["artifact_bytes_verified"])
        self.assertFalse(report["software_checks_passed"])
        self.assertEqual(report["declaration"]["findings"], ["calibration_interval"])

    def test_no_references_cannot_vacuously_verify(self):
        doc = declaration()
        doc["records"] = []
        report = self.verify(doc, {})
        self.assertFalse(report["artifact_bytes_verified"])
        self.assertFalse(report["software_checks_passed"])
        self.assertEqual(report["artifact_findings"], ["artifact_references_empty"])

    def test_valid_empty_artifact_and_missing_artifact_are_distinct(self):
        doc = declaration(EMPTY)
        self.assertTrue(self.verify(doc, {EMPTY: b""})["artifact_bytes_verified"])
        self.assertEqual(self.verify(doc, {})["artifact_findings"], ["artifact_missing"])

    def test_exact_types_and_malformed_manifest_fail_with_fixed_error(self):
        class DictSubclass(dict):
            pass

        class BytesSubclass(bytes):
            pass

        for supplied in (
            None,
            [],
            DictSubclass(),
            {ABC: bytearray(b"abc")},
            {ABC: memoryview(b"abc")},
            {ABC: BytesSubclass(b"abc")},
            {ABC: "abc"},
            {True: b"abc"},
            {ABC.upper(): b"abc"},
            {"PRIVATE_PATH": b"abc"},
        ):
            with self.subTest(supplied=type(supplied)):
                with self.assertRaisesRegex(ValueError, "^invalid_qualification_artifacts$"):
                    self.verify(declaration(), supplied)
        for malformed in (b"{PRIVATE_CONTENT", b'{"version":1,"version":1}', b"[]"):
            with self.assertRaisesRegex(ValueError, "^invalid_qualification_artifacts$"):
                self.verify(malformed, {ABC: b"abc"})
        with self.assertRaisesRegex(ValueError, "^invalid_qualification_artifacts$"):
            self.verify(declaration(), {ABC: b"abc"}, now_ms=True)

    def test_artifact_byte_and_entry_budgets(self):
        payload = b"x" * 1048576
        digest = hashlib.sha256(payload).hexdigest()
        self.assertTrue(
            self.verify(declaration(digest), {digest: payload})["artifact_bytes_verified"]
        )
        with self.assertRaisesRegex(ValueError, "^invalid_qualification_artifacts$"):
            self.verify(declaration(digest), {digest: payload + b"x"})
        four = {format(i, "064x"): payload for i in range(4)}
        self.assertEqual(
            self.verify(declaration(), four)["artifact_counts"]["supplied_bytes"], 4194304
        )
        four["f" * 64] = b"x"
        with self.assertRaisesRegex(ValueError, "^invalid_qualification_artifacts$"):
            self.verify(declaration(), four)
        fifteen = {format(i, "064x"): b"" for i in range(15)}
        self.assertEqual(self.verify(declaration(), fifteen)["artifact_counts"]["supplied"], 15)
        fifteen["f" * 64] = b""
        with self.assertRaisesRegex(ValueError, "^invalid_qualification_artifacts$"):
            self.verify(declaration(), fifteen)

    def test_supplied_order_and_declared_evidence_do_not_create_authority(self):
        doc = declaration()
        doc["records"][0]["artifact_sha256"] = EMPTY
        for row in doc["records"]:
            row["evidence"] = "external_unverified"
        first = self.verify(doc, {ABC: b"abc", EMPTY: b""})
        self.assertEqual(first, self.verify(doc, {EMPTY: b"", ABC: b"abc"}))
        self.assertTrue(first["artifact_bytes_verified"])
        self.assertFalse(first["physical_qualification_passed"])
        self.assertFalse(first["artifact_authenticity_verified"])


if __name__ == "__main__":
    unittest.main()
