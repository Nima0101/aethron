"""Synthetic review declarations; no legal review or real data-use authority."""

import copy
import importlib
import importlib.util
import unittest

import test_candidate_holdout as fixtures


class CandidateRights(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.CandidateHoldout()
        fixture.setUp()
        self.candidate = fixture.candidate
        self.manifest = fixtures.encode(fixture.training)
        self.doc = {
            "version": 1,
            "review_sha256": fixtures.sha(b"independently reviewed synthetic evidence"),
            "status": "approved",
            "uses": ["offline_evaluation"],
            "valid_from_s": 100,
            "expires_at_s": 200,
        }
        for key in (
            "artifact_sha256",
            "preprocessing_sha256",
            "protocol_sha256",
            "training_manifest_sha256",
        ):
            self.doc[key] = self.candidate[key]

    def api(self):
        self.assertIsNotNone(
            importlib.util.find_spec("aethron.evaluation.rights"), "rights gate missing"
        )
        return importlib.import_module("aethron.evaluation.rights")

    def inputs(self, raw=None):
        raw = fixtures.encode(self.doc) if raw is None else raw
        self.candidate["rights_sha256"] = fixtures.sha(raw)
        candidate = fixtures.encode(self.candidate)
        args = {
            "expected_candidate_sha256": fixtures.sha(candidate),
            "expected_manifest_sha256": fixtures.sha(self.manifest),
            "expected_protocol_sha256": self.candidate["protocol_sha256"],
            "expected_review_sha256": fixtures.sha(b"independently reviewed synthetic evidence"),
            "operation": "offline_evaluation",
            "now_s": 150,
            "minimum_time_s": 100,
            "revoked_rights_sha256s": (),
        }
        return raw, candidate, args

    def assess(self, raw=None, **changes):
        raw, candidate, args = self.inputs(raw)
        args.update(changes)
        return self.api().assess(raw, candidate, self.manifest, **args)

    def test_active_scope_is_declaration_only(self):
        result = self.assess()
        self.assertTrue(result["declared_permission"])
        self.assertEqual(result["reason"], "declared_scope_active")
        self.assertEqual(result["rights_sha256"], fixtures.sha(fixtures.encode(self.doc)))
        self.assertEqual(result["review_sha256"], self.doc["review_sha256"])
        for key in ("rights_verified", "review_verified", "dataset_rights_verified", "qualified"):
            self.assertIs(result[key], False)

    def test_report_binds_revocation_set_and_clock_floor(self):
        result = self.assess()
        self.assertIn("revocations_sha256", result)
        self.assertEqual(result["minimum_time_s"], 100)
        other = self.assess(revoked_rights_sha256s=("0" * 64, "1" * 64))
        reordered = self.assess(revoked_rights_sha256s=("1" * 64, "0" * 64, "0" * 64))
        self.assertEqual(other, reordered)
        self.assertNotEqual(other["revocations_sha256"], result["revocations_sha256"])
        self.assertEqual(self.assess(minimum_time_s=101)["minimum_time_s"], 101)

    def test_negative_review_states_and_unlisted_use_deny(self):
        for status in ("pending", "denied", "revoked"):
            self.doc["status"] = status
            result = self.assess()
            self.assertFalse(result["declared_permission"])
            self.assertEqual(result["reason"], "review_" + status)
        self.doc["status"] = "approved"
        for use in ("offline_training", "artifact_redistribution"):
            result = self.assess(operation=use)
            self.assertFalse(result["declared_permission"])
            self.assertEqual(result["reason"], "out_of_scope")

    def test_time_boundaries_and_external_revocation_deny(self):
        for now, floor, allowed, reason in (
            (99, 0, False, "not_yet_valid"),
            (100, 100, True, "declared_scope_active"),
            (199, 100, True, "declared_scope_active"),
            (200, 100, False, "expired"),
            (201, 100, False, "expired"),
        ):
            result = self.assess(now_s=now, minimum_time_s=floor)
            self.assertEqual((result["declared_permission"], result["reason"]), (allowed, reason))
        record_hash = fixtures.sha(fixtures.encode(self.doc))
        result = self.assess(revoked_rights_sha256s=(record_hash,))
        self.assertEqual(
            (result["declared_permission"], result["reason"]), (False, "record_revoked")
        )
        self.assertTrue(self.assess(revoked_rights_sha256s=("0" * 64,))["declared_permission"])

    def test_invalid_trusted_inputs_reject_instead_of_becoming_permission(self):
        for key, value in (
            ("now_s", True),
            ("now_s", -1),
            ("now_s", 2**53),
            ("now_s", 150.0),
            ("now_s", 99),
            ("minimum_time_s", 151),
            ("minimum_time_s", False),
            ("operation", "live_inference"),
            ("operation", None),
            ("revoked_rights_sha256s", "0" * 64),
            ("revoked_rights_sha256s", ["0" * 64]),
            ("revoked_rights_sha256s", (None,)),
            ("revoked_rights_sha256s", ("0" * 64,) * 1025),
            ("expected_review_sha256", "0" * 64),
        ):
            with (
                self.subTest(key=key, value=value),
                self.assertRaisesRegex(ValueError, "^invalid_candidate_rights$"),
            ):
                self.assess(**{key: value})

    def test_candidate_bindings_and_review_pin_must_match(self):
        for key in (
            "artifact_sha256",
            "preprocessing_sha256",
            "protocol_sha256",
            "training_manifest_sha256",
            "review_sha256",
        ):
            original = self.doc[key]
            self.doc[key] = "0" * 64
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(ValueError, "^invalid_candidate_rights$"),
            ):
                self.assess()
            self.doc[key] = original
        raw, candidate, args = self.inputs()
        with self.assertRaisesRegex(ValueError, "^invalid_candidate_rights$"):
            self.api().assess(raw + b" ", candidate, self.manifest, **args)
        for pin in (
            "expected_candidate_sha256",
            "expected_manifest_sha256",
            "expected_protocol_sha256",
        ):
            with (
                self.subTest(pin=pin),
                self.assertRaisesRegex(ValueError, "^invalid_candidate_rights$"),
            ):
                self.assess(**{pin: "0" * 64})

    def test_closed_schema_and_nonempty_approved_scope(self):
        original = copy.deepcopy(self.doc)
        for key in original:
            self.doc = copy.deepcopy(original)
            del self.doc[key]
            with (
                self.subTest(missing=key),
                self.assertRaisesRegex(ValueError, "^invalid_candidate_rights$"),
            ):
                self.assess()
        for key, value in (
            ("version", True),
            ("status", "unknown"),
            ("status", ["approved"]),
            ("uses", []),
            ("uses", ["offline_evaluation"] * 2),
            ("uses", [["offline_evaluation"]]),
            ("uses", ["weapons"]),
            ("valid_from_s", True),
            ("expires_at_s", 100),
            ("expires_at_s", 2**53),
            ("rights_verified", True),
            ("reviewer_name", "private"),
        ):
            self.doc = copy.deepcopy(original)
            self.doc[key] = value
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(ValueError, "^invalid_candidate_rights$"),
            ):
                self.assess()
        self.doc = copy.deepcopy(original)
        self.doc.update(status="pending", uses=[])
        self.assertFalse(self.assess()["declared_permission"])

    def test_strict_document_bounds(self):
        raw = fixtures.encode(self.doc)
        padded = raw.ljust(16384, b" ")
        self.assertTrue(self.assess(padded)["declared_permission"])
        for data in (
            padded + b" ",
            b"null",
            b"NaN",
            b"\xff",
            bytearray(raw),
            raw[:-1] + b',"version":1}',
            b"[" * 9 + b"]" * 9,
        ):
            with (
                self.subTest(kind=type(data)),
                self.assertRaisesRegex(ValueError, "^invalid_candidate_rights$"),
            ):
                self.assess(data)
