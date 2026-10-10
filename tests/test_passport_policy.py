"""Policy admission is independent of individual software-statement success."""

import copy
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron import passports

HAS_CRYPTO = importlib.util.find_spec("cryptography") is not None


class PinnedPolicyTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "examples/passports/vectors.json"
        self.case = json.loads(path.read_bytes())["cases"][0]
        self.raw = self.case["policy"].encode("utf-8")
        self.policy = json.loads(self.raw)
        self.arguments = {
            "expected_policy_sha256": hashlib.sha256(self.raw).hexdigest(),
            "now_s": 1500,
            "minimum_time_s": 1400,
            "minimum_policy_revision": 3,
        }

    def validate(self, raw=None, **overrides):
        validator = getattr(passports, "validate_pinned_policy", None)
        self.assertTrue(callable(validator), "public pinned-policy validation is missing")
        return validator(self.raw if raw is None else raw, **(self.arguments | overrides))

    def assert_rejected(self, result, reason):
        self.assertEqual((result.status, result.reason), ("rejected", reason))
        self.assertIsNone(result.policy_sha256)
        self.assertIsNone(result.policy_revision)
        self.assertIsNone(result.expires_at)
        self.assertFalse(result.motion_authority)
        self.assertFalse(result.execution_authority)
        self.assertFalse(result.evidence_verified)

    def test_exact_policy_metadata_without_authority(self):
        result = self.validate()
        self.assertEqual((result.status, result.reason), ("validated", "policy_matches"))
        self.assertEqual(result.policy_sha256, self.arguments["expected_policy_sha256"])
        self.assertEqual((result.policy_revision, result.expires_at), (3, 2100))
        self.assertFalse(result.motion_authority)
        self.assertFalse(result.execution_authority)
        self.assertFalse(result.evidence_verified)

    @unittest.skipUnless(HAS_CRYPTO, "requires optional passport crypto backend")
    def test_policy_can_revoke_every_available_signer(self):
        control = passports.verify(
            self.case["envelope"].encode(), self.raw, **self.case["arguments"]
        )
        self.assertEqual(control.status, "authenticated")
        self.policy["revision"] = 4
        self.policy["revoked_keys"] = [self.policy["keys"][0]["key_id"]]
        raw = json.dumps(self.policy).encode()
        result = self.validate(raw, expected_policy_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual((result.status, result.policy_revision), ("validated", 4))
        rejected = passports.verify(self.case["envelope"].encode(), raw, **self.case["arguments"])
        self.assertEqual((rejected.status, rejected.reason), ("rejected", "revoked"))
        self.assertIsNone(rejected.policy_revision)
        self.assert_rejected(self.validate(minimum_policy_revision=4), "policy_rollback")

    def test_digest_binds_exact_bytes_without_requiring_canonical_json(self):
        pretty = json.dumps(self.policy, indent=2).encode()
        self.assertNotEqual(pretty, self.raw)
        self.assert_rejected(self.validate(pretty), "policy_mismatch")
        digest = hashlib.sha256(pretty).hexdigest()
        result = self.validate(pretty, expected_policy_sha256=digest)
        self.assertEqual((result.status, result.policy_sha256), ("validated", digest))
        self.assert_rejected(self.validate(expected_policy_sha256="0" * 64), "policy_mismatch")

    def test_time_and_revision_floors_and_half_open_interval(self):
        for overrides, reason in (
            ({"now_s": 1399}, "time_rollback"),
            ({"minimum_policy_revision": 4}, "policy_rollback"),
            ({"now_s": 899, "minimum_time_s": 0}, "policy_not_current"),
            ({"now_s": 2100}, "policy_not_current"),
        ):
            with self.subTest(overrides=overrides):
                self.assert_rejected(self.validate(**overrides), reason)
        for now in (900, 2099):
            self.assertEqual(self.validate(now_s=now, minimum_time_s=0).status, "validated")

    def test_all_policy_fields_are_checked_even_with_matching_digest(self):
        documents = []
        for key, value in (
            ("version", True),
            ("revision", 0),
            ("expires_at", 4501),
            ("keys", []),
            ("revoked_keys", ["z" * 64]),
            ("revoked_evidence", ["0" * 64] * 2),
            ("revoked_passports", ["x"] * 257),
        ):
            doc = copy.deepcopy(self.policy)
            doc[key] = value
            documents.append(json.dumps(doc).encode())
        doc = copy.deepcopy(self.policy)
        doc["keys"].append(dict(doc["keys"][0], key_id="0" * 64))
        documents.append(json.dumps(doc).encode())
        documents.extend(
            [
                self.raw.replace(b'"revision":3', b'"revision":3,"revision":3'),
                self.raw.replace(b'"revision":3', b'"revision":3.0'),
                self.raw.replace(b'"revision":3', b'"revision":3e0'),
                self.raw.replace(b'"revision":3', b'"revision":9007199254740992'),
                self.raw[:-1] + b',"extra":false}',
                self.raw.decode().encode("utf-16"),
                b"\xff",
                b"null",
            ]
        )
        for raw in documents:
            with self.subTest(raw=raw[:80]):
                self.assert_rejected(
                    self.validate(raw, expected_policy_sha256=hashlib.sha256(raw).hexdigest()),
                    "invalid_input",
                )

    def test_strict_caller_inputs(self):
        for field, values in (
            ("expected_policy_sha256", [None, "A" * 64, "0" * 64 + "\n", b"0" * 64]),
            ("now_s", [True, -1, 1.0, 2**53]),
            ("minimum_time_s", [False, -1, 1.0, 2**53]),
            ("minimum_policy_revision", [True, 0, 1.0, 2**53]),
        ):
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assert_rejected(self.validate(**{field: value}), "invalid_input")

    def test_bounds_and_immutable_inputs_before_hashing(self):
        with patch.object(passports.hashlib, "sha256", side_effect=AssertionError("hashed")):
            for raw in (b" " * 65537, b"[" * 9 + b"]" * 9, bytearray(self.raw), "{}"):
                with self.subTest(kind=type(raw).__name__):
                    self.assert_rejected(self.validate(raw), "invalid_input")

    def test_check_has_no_implicit_clock_or_persisted_floor(self):
        self.assert_rejected(self.validate(now_s=2100), "policy_not_current")
        self.assertEqual(self.validate().status, "validated")
        self.assert_rejected(self.validate(minimum_time_s=2100), "time_rollback")
        with patch.dict("sys.modules", {"cryptography": None}):
            self.assertEqual(self.validate().status, "validated")
