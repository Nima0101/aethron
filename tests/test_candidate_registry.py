"""Synthetic immutable entries; byte bindings do not establish evaluation results."""

import copy
import importlib
import importlib.util
import json
import unittest

import test_candidate_cards as card_fixtures
import test_candidate_holdout as fixtures
import test_candidate_rights as rights_fixtures


class CandidateRegistry(unittest.TestCase):
    def setUp(self):
        holdout = fixtures.CandidateHoldout()
        holdout.setUp()
        card = card_fixtures.CandidateCards()
        card.setUp()
        rights = rights_fixtures.CandidateRights()
        rights.setUp()
        self.review = rights.doc["review_sha256"]
        self.candidate = holdout.candidate
        self.card = card.card
        self.documents = {
            "rights": fixtures.encode(rights.doc),
            "training_manifest": rights.manifest,
            "evaluation_manifest": fixtures.encode(holdout.evaluation),
            "evaluation_evidence": b'{"qualified":true,"private":"synthetic payload"}',
        }
        self.bind_records()
        self.entry = {
            "version": 1,
            "kind": "offline_candidate",
            "protocol_sha256": self.candidate["protocol_sha256"],
        }
        self.bind_entry()

    def bind_records(self):
        self.candidate["rights_sha256"] = fixtures.sha(self.documents["rights"])
        self.card["rights_sha256"] = self.candidate["rights_sha256"]
        self.documents["card"] = fixtures.encode(self.card)
        self.candidate["card_sha256"] = fixtures.sha(self.documents["card"])
        self.documents["candidate"] = fixtures.encode(self.candidate)

    def bind_entry(self):
        self.entry["documents"] = {
            role: {"sha256": fixtures.sha(raw), "bytes": len(raw)}
            for role, raw in self.documents.items()
        }

    def validate(self, raw=None, **changes):
        self.assertIsNotNone(
            importlib.util.find_spec("aethron.evaluation.registry"), "registry gate missing"
        )
        api = importlib.import_module("aethron.evaluation.registry")
        raw = fixtures.encode(self.entry) if raw is None else raw
        args = {
            **self.documents,
            "expected_entry_sha256": fixtures.sha(raw),
            "expected_review_sha256": self.review,
            "now_s": 150,
            "minimum_time_s": 100,
            "revoked_rights_sha256s": (),
        }
        args.update(changes)
        return api.validate(raw, **args)

    def test_valid_entry_reports_bindings_without_promoting_opaque_evidence(self):
        report = self.validate()
        self.assertEqual(report, self.validate())
        self.assertEqual(report["entry_sha256"], fixtures.sha(fixtures.encode(self.entry)))
        self.assertEqual(report["documents"], self.entry["documents"])
        self.assertEqual(report["protocol_sha256"], self.entry["protocol_sha256"])
        for key in (
            "registry_entry_valid",
            "card_structure_valid",
            "declared_test_separation",
            "rights_declaration_active",
            "evaluation_bytes_verified",
        ):
            self.assertIs(report[key], True)
        for key in (
            "evaluation_semantics_verified",
            "model_artifacts_verified",
            "rights_verified",
            "review_verified",
            "dataset_rights_verified",
            "qualified",
            "runtime_admitted",
        ):
            self.assertIs(report[key], False)
        self.assertEqual(report["rights_reason"], "declared_scope_active")
        self.assertEqual(report["review_sha256"], self.review)
        self.assertEqual(report["minimum_time_s"], 100)
        self.assertEqual(report["evaluated_at_s"], 150)
        self.assertNotIn("synthetic payload", json.dumps(report))
        self.assertNotIn(self.card["source"], json.dumps(report))

    def test_every_document_requires_exact_digest_size_and_bytes(self):
        original = copy.deepcopy(self.entry)
        for role, raw in self.documents.items():
            for replacement in (raw + b" ", bytearray(raw), None):
                with self.subTest(role=role, mutation=type(replacement).__name__):
                    with self.assertRaisesRegex(ValueError, "^invalid_registry_entry$"):
                        self.validate(**{role: replacement})
            for field, value in (
                ("sha256", "0" * 64),
                ("bytes", True),
                ("bytes", len(raw) - 1),
                ("bytes", 0),
                ("bytes", 2**53),
                ("url", "https://invalid.example"),
            ):
                self.entry = copy.deepcopy(original)
                self.entry["documents"][role][field] = value
                with self.subTest(role=role, field=field, value=value):
                    with self.assertRaisesRegex(ValueError, "^invalid_registry_entry$"):
                        self.validate()
            self.entry = copy.deepcopy(original)

    def test_external_pins_and_time_floor_are_mandatory(self):
        for key, value in (
            ("expected_entry_sha256", "0" * 64),
            ("expected_entry_sha256", True),
            ("expected_review_sha256", "0" * 64),
            ("minimum_time_s", 151),
            ("now_s", True),
            ("revoked_rights_sha256s", []),
        ):
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "^invalid_registry_entry$"):
                    self.validate(**{key: value})

    def test_rebound_invalid_card_still_rejects(self):
        self.card["artifact_sha256"] = "0" * 64
        self.bind_records()
        self.bind_entry()
        with self.assertRaisesRegex(ValueError, "^invalid_registry_entry$"):
            self.validate()

    def test_rebound_evaluation_leakage_and_protocol_disagreement_reject(self):
        original = json.loads(self.documents["evaluation_manifest"])
        train = json.loads(self.documents["training_manifest"])
        for field in ("source_sha256", "session_sha256"):
            evaluation = copy.deepcopy(original)
            evaluation["samples"][2][field] = train["samples"][0][field]
            self.documents["evaluation_manifest"] = fixtures.encode(evaluation)
            self.bind_entry()
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "^invalid_registry_entry$"):
                    self.validate()
        original["protocol_sha256"] = "0" * 64
        self.documents["evaluation_manifest"] = fixtures.encode(original)
        self.bind_entry()
        with self.assertRaisesRegex(ValueError, "^invalid_registry_entry$"):
            self.validate()

    def test_expiry_revocation_and_negative_review_preserve_denial(self):
        for changes, reason in (
            ({"now_s": 200}, "expired"),
            (
                {"revoked_rights_sha256s": (fixtures.sha(self.documents["rights"]),)},
                "record_revoked",
            ),
        ):
            report = self.validate(**changes)
            self.assertTrue(report["registry_entry_valid"])
            self.assertFalse(report["rights_declaration_active"])
            self.assertEqual(report["rights_reason"], reason)
            self.assertFalse(report["qualified"])
        record = json.loads(self.documents["rights"])
        for status in ("denied", "pending", "revoked"):
            record["status"] = status
            self.documents["rights"] = fixtures.encode(record)
            self.bind_records()
            self.bind_entry()
            report = self.validate()
            self.assertFalse(report["rights_declaration_active"])
            self.assertEqual(report["rights_reason"], "review_" + status)

    def test_report_binds_revocation_set_independent_of_order(self):
        report = self.validate(revoked_rights_sha256s=("0" * 64, "1" * 64))
        reordered = self.validate(revoked_rights_sha256s=("1" * 64, "0" * 64, "0" * 64))
        self.assertEqual(report, reordered)
        self.assertNotEqual(report["revocations_sha256"], self.validate()["revocations_sha256"])

    def test_closed_entry_schema_and_bounded_strict_json(self):
        original = copy.deepcopy(self.entry)
        for key, value in (
            ("version", True),
            ("version", 2),
            ("kind", "live_candidate"),
            ("protocol_sha256", "0" * 64),
            ("qualified", True),
            ("documents", {}),
            ("documents", dict(self.entry["documents"], extra={})),
        ):
            self.entry = dict(original, **{key: value})
            with self.subTest(key=key, value=value):
                with self.assertRaisesRegex(ValueError, "^invalid_registry_entry$"):
                    self.validate()
        self.entry = original
        raw = fixtures.encode(original)
        self.assertTrue(self.validate(raw.ljust(16384, b" "))["registry_entry_valid"])
        for invalid in (
            raw.ljust(16385, b" "),
            b'{"version":1,' + raw[1:],
            b"[]",
            b"NaN",
            b"[" * 9 + b"0" + b"]" * 9,
            b"\xff",
            bytearray(raw),
        ):
            with self.assertRaisesRegex(ValueError, "^invalid_registry_entry$"):
                self.validate(invalid)

    def test_opaque_evidence_is_bounded_even_when_rebound(self):
        self.documents["evaluation_evidence"] = b"x" * (2 * 1024 * 1024)
        self.bind_entry()
        self.assertTrue(self.validate()["evaluation_bytes_verified"])
        for raw in (b"", self.documents["evaluation_evidence"] + b"x"):
            self.documents["evaluation_evidence"] = raw
            self.bind_entry()
            with self.assertRaisesRegex(ValueError, "^invalid_registry_entry$"):
                self.validate()


if __name__ == "__main__":
    unittest.main()
