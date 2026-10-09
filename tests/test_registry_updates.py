"""Offline update proposals never commit state or authorize a deployment."""

import importlib
import importlib.util
import json
import unittest

import test_candidate_holdout as fixtures
import test_candidate_registry as registry_fixtures


class RegistryUpdates(unittest.TestCase):
    def setUp(self):
        self.registry = registry_fixtures.CandidateRegistry()
        self.registry.setUp()
        self.entry = fixtures.encode(self.registry.entry)
        self.previous = fixtures.sha(b"previous independently pinned registry entry")
        self.doc = {
            "version": 1,
            "kind": "offline_registry_update",
            "previous_entry_sha256": self.previous,
            "entry_sha256": fixtures.sha(self.entry),
            "revision": 8,
            "valid_from_s": 110,
            "expires_at_s": 180,
        }

    def validate(self, raw=None, **changes):
        self.assertIsNotNone(
            importlib.util.find_spec("aethron.evaluation.updates"), "update validator missing"
        )
        raw = fixtures.encode(self.doc) if raw is None else raw
        args = {
            **self.registry.documents,
            "expected_proposal_sha256": fixtures.sha(raw),
            "expected_current_entry_sha256": self.previous,
            "current_revision": 7,
            "minimum_revision": 6,
            "expected_review_sha256": self.registry.review,
            "now_s": 150,
            "minimum_time_s": 100,
        }
        args["revoked_rights_sha256s"] = ()
        args.update(changes)
        return importlib.import_module("aethron.evaluation.updates").validate(
            raw, self.entry, **args
        )

    def test_pinned_success_binds_state_without_committing_or_admitting(self):
        result = self.validate()
        self.assertEqual(result, self.validate())
        self.assertTrue(result["proposal_structure_valid"])
        self.assertTrue(result["declaration_checks_passed"])
        self.assertEqual(result["proposal_reason"], "declared_window_active")
        self.assertEqual(result["proposal_sha256"], fixtures.sha(fixtures.encode(self.doc)))
        self.assertEqual(result["previous_entry_sha256"], self.previous)
        self.assertEqual(result["current_revision"], 7)
        self.assertEqual(result["minimum_revision"], 6)
        self.assertEqual(result["revision"], 8)
        self.assertEqual(result["registry"]["entry_sha256"], fixtures.sha(self.entry))
        for field in ("state_committed", "signatures_verified", "qualified", "runtime_admitted"):
            self.assertIs(result[field], False)

    def test_rebound_rollback_skip_and_wrong_predecessor_reject(self):
        for field, value in (
            ("revision", 7),
            ("revision", 6),
            ("revision", 9),
            ("revision", True),
            ("revision", 2**53),
            ("previous_entry_sha256", "0" * 64),
            ("entry_sha256", self.previous),
        ):
            original = self.doc[field]
            self.doc[field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(ValueError, "^invalid_registry_update$"):
                    self.validate()
            self.doc[field] = original

    def test_external_pins_and_revision_floor_fail_closed(self):
        for key, value in (
            ("expected_proposal_sha256", "0" * 64),
            ("expected_current_entry_sha256", "0" * 64),
            ("current_revision", 6),
            ("current_revision", True),
            ("current_revision", -1),
            ("current_revision", 2**53),
            ("minimum_revision", 8),
            ("minimum_revision", False),
            ("minimum_revision", -1),
            ("minimum_time_s", 151),
            ("expected_review_sha256", "0" * 64),
        ):
            with self.subTest(key=key, value=value):
                with self.assertRaisesRegex(ValueError, "^invalid_registry_update$"):
                    self.validate(**{key: value})
        self.doc["revision"] = 2**53 - 1
        self.assertTrue(self.validate(current_revision=2**53 - 2)["declaration_checks_passed"])
        with self.assertRaisesRegex(ValueError, "^invalid_registry_update$"):
            self.validate(current_revision=2**53 - 1)

    def test_expiry_boundaries_keep_negative_evidence(self):
        for now, active, reason in (
            (109, False, "not_yet_valid"),
            (110, True, "declared_window_active"),
            (179, True, "declared_window_active"),
            (180, False, "expired"),
        ):
            report = self.validate(now_s=now)
            self.assertEqual(report["declaration_checks_passed"], active)
            self.assertEqual(report["proposal_reason"], reason)
            self.assertEqual(report["registry"]["evaluated_at_s"], now)
            self.assertFalse(report["state_committed"])

    def test_active_proposal_cannot_promote_expired_or_revoked_rights(self):
        self.doc["expires_at_s"] = 250
        for args, reason in (
            ({"now_s": 200}, "expired"),
            (
                {"revoked_rights_sha256s": (fixtures.sha(self.registry.documents["rights"]),)},
                "record_revoked",
            ),
        ):
            report = self.validate(**args)
            self.assertEqual(report["proposal_reason"], "declared_window_active")
            self.assertFalse(report["declaration_checks_passed"])
            self.assertEqual(report["registry"]["rights_reason"], reason)
            self.assertFalse(report["qualified"])

    def test_revalidation_cannot_be_replaced_by_a_forged_report(self):
        with self.assertRaisesRegex(ValueError, "^invalid_registry_update$"):
            self.validate(candidate=b'{"registry_entry_valid":true}')
        candidate = json.loads(self.registry.documents["candidate"])
        candidate["training_split"] = "test"
        self.registry.documents["candidate"] = fixtures.encode(candidate)
        self.registry.bind_entry()
        self.entry = fixtures.encode(self.registry.entry)
        self.doc["entry_sha256"] = fixtures.sha(self.entry)
        with self.assertRaisesRegex(ValueError, "^invalid_registry_update$"):
            self.validate()

    def test_predecessor_change_rejects_replay_and_same_entry_rejects(self):
        self.validate()
        with self.assertRaisesRegex(ValueError, "^invalid_registry_update$"):
            self.validate(
                expected_current_entry_sha256=fixtures.sha(self.entry), current_revision=8
            )
        self.doc["previous_entry_sha256"] = fixtures.sha(self.entry)
        with self.assertRaisesRegex(ValueError, "^invalid_registry_update$"):
            self.validate(expected_current_entry_sha256=fixtures.sha(self.entry))

    def test_closed_schema_strict_times_and_byte_bounds(self):
        original = self.doc.copy()
        for field, value in (
            ("version", True),
            ("version", 2),
            ("kind", "deploy"),
            ("valid_from_s", True),
            ("valid_from_s", -1),
            ("valid_from_s", 180),
            ("expires_at_s", 110),
            ("expires_at_s", 2**53),
            ("qualified", True),
            ("signatures", []),
        ):
            self.doc = dict(original, **{field: value})
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(ValueError, "^invalid_registry_update$"):
                    self.validate()
        self.doc = original
        raw = fixtures.encode(original)
        self.assertTrue(self.validate(raw.ljust(4096, b" "))["proposal_structure_valid"])
        for invalid in (
            raw.ljust(4097, b" "),
            b'{"version":1,' + raw[1:],
            b"NaN",
            b"[]",
            b"[" * 9 + b"0" + b"]" * 9,
            bytearray(raw),
            b"\xff",
        ):
            with self.assertRaisesRegex(ValueError, "^invalid_registry_update$"):
                self.validate(invalid)


if __name__ == "__main__":
    unittest.main()
