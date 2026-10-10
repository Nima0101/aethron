"""P16.1 synthetic statements; signing seeds here are public test data only."""

import base64
import copy
import hashlib
import json
import random
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron import passports

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
except ImportError:
    Ed25519PrivateKey = None


def wire(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("ascii")


def b64(value):
    return base64.b64encode(value).decode("ascii")


def payload():
    return {
        "version": 1,
        "passport_id": "fixture-statement-1",
        "issuer": "fixture-publisher",
        "subject_sha256": "a" * 64,
        "issued_at": 1000,
        "expires_at": 2000,
        "assurance": "self_declared",
        "motion_authority": False,
        "capabilities": [{"name": "perception.direct.v3", "evidence_sha256": ["b" * 64, "c" * 64]}],
        "evidence": [
            {"sha256": "b" * 64, "kind": "synthetic", "outcome": "passed"},
            {"sha256": "c" * 64, "kind": "recorded", "outcome": "failed"},
        ],
    }


class PassportSchemaTests(unittest.TestCase):
    def test_canonical_and_negative_evidence_retained(self):
        value = payload()
        self.assertEqual(passports.canonicalize(json.dumps(value, indent=2).encode()), wire(value))
        self.assertIn(b'"outcome":"failed"', passports.canonicalize(wire(value)))

    def test_closed_schema_and_resource_bounds(self):
        invalid = [b"{}", b"null", b"[]", b"\xff", b" " * 65537, b"[" * 9 + b"]" * 9]
        for field, value in (
            ("version", True),
            ("issued_at", False),
            ("issued_at", 1.0),
            ("issued_at", -1),
            ("expires_at", 2**53),
            ("expires_at", 1000),
            ("expires_at", 87401),
            ("motion_authority", True),
            ("motion_authority", 0),
            ("assurance", "accredited"),
            ("issuer", "private/name"),
            ("issuer", "\ud800"),
            ("capabilities", []),
            ("evidence", []),
        ):
            value_doc = payload()
            value_doc[field] = value
            invalid.append(wire(value_doc))
        value_doc = payload()
        value_doc["person_id"] = "forbidden"
        invalid.append(wire(value_doc))
        invalid += [
            wire(payload()).replace(b'"version":1', replacement)
            for replacement in (
                b'"version":1,"version":1',
                b'"version":NaN',
                b'"version":1e0',
            )
        ]
        for raw in invalid + [None, "{}", bytearray(b"{}")]:
            with self.subTest(raw=str(raw)[:80]):
                with self.assertRaisesRegex(ValueError, "^invalid_passport$"):
                    passports.canonicalize(raw)

    def test_integer_tokens_rejected_before_shape_validation(self):
        for token in (b"9" * 3000, b"9" * 17, b"9007199254740992", b"-1"):
            raw = wire(payload()).replace(b'"version":1', b'"version":' + token)
            with self.subTest(length=len(token)):
                with patch.object(
                    passports, "_payload", side_effect=AssertionError("integer reached schema")
                ):
                    with self.assertRaisesRegex(ValueError, "^invalid_passport$"):
                        passports.canonicalize(raw)

    def test_safe_integer_lexical_boundaries(self):
        self.assertEqual(passports._parse(b"9007199254740991"), passports.MAX_INTEGER)
        self.assertEqual(passports._parse(b"0"), 0)
        self.assertEqual(passports._parse(b"-0"), 0)

    def test_bounds_before_json_allocation(self):
        with patch.object(passports.json, "loads", side_effect=AssertionError("allocated")):
            for raw in (b" " * 65537, b"[" * 9):
                with self.assertRaisesRegex(ValueError, "^invalid_passport$"):
                    passports.canonicalize(raw)

    def test_capability_references_and_forbidden_extensions(self):
        cases = []
        for name in ("motion.follow", "weapon.integration", "person.reidentification", "unknown"):
            doc = payload()
            doc["capabilities"][0]["name"] = name
            cases.append(doc)
        for section in ("capabilities", "evidence"):
            doc = payload()
            doc[section].append(copy.deepcopy(doc[section][0]))
            cases.append(doc)
            doc = payload()
            doc[section][0]["extra"] = False
            cases.append(doc)
        for refs in (["d" * 64], ["b" * 64], ["b" * 64] * 2, []):
            doc = payload()
            doc["capabilities"][0]["evidence_sha256"] = refs
            cases.append(doc)
        for doc in cases:
            with self.subTest(doc=doc):
                with self.assertRaisesRegex(ValueError, "^invalid_passport$"):
                    passports.canonicalize(wire(doc))

    def test_pae_golden(self):
        self.assertEqual(
            passports.pae(b"abc"),
            b"DSSEv1 51 application/vnd.aethron.capability-passport.v1+json 3 abc",
        )

    def test_seeded_bounded_mutations(self):
        rng = random.Random(1601)
        original = wire(payload())
        for _ in range(256):
            raw = bytearray(original)
            raw[rng.randrange(len(raw))] = rng.randrange(256)
            try:
                canonical = passports.canonicalize(bytes(raw))
                self.assertEqual(passports.canonicalize(canonical), canonical)
            except ValueError as exc:
                self.assertEqual(str(exc), "invalid_passport")

    def test_missing_crypto_rejects_without_fallback(self):
        root = Path(__file__).resolve().parents[1] / "examples/passports"
        case = json.loads((root / "vectors.json").read_bytes())["cases"][0]
        with patch.dict("sys.modules", {"cryptography": None}):
            with patch.dict(
                "sys.modules", {"cryptography.hazmat.primitives.asymmetric.ed25519": None}
            ):
                result = passports.verify(
                    case["envelope"].encode(), case["policy"].encode(), **case["arguments"]
                )
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reason, "crypto_unavailable")
        self.assertFalse(result.motion_authority)


@unittest.skipIf(Ed25519PrivateKey is None, "install passports extra for real Ed25519 tests")
class PassportVerificationTests(unittest.TestCase):
    def setUp(self):
        # Public RFC 8032 test seed, intentionally not a secret or deployment key.
        self.private = Ed25519PrivateKey.from_private_bytes(
            bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        )
        self.public = self.private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.key_id = hashlib.sha256(self.public).hexdigest()
        self.policy = {
            "version": 1,
            "revision": 3,
            "issued_at": 900,
            "expires_at": 2100,
            "keys": [
                {
                    "key_id": self.key_id,
                    "issuer": "fixture-publisher",
                    "public_key": self.public.hex(),
                    "not_before": 800,
                    "expires_at": 3000,
                    "capabilities": ["perception.direct.v3"],
                }
            ],
            "revoked_passports": [],
            "revoked_keys": [],
            "revoked_evidence": [],
        }
        self.document = payload()

    def envelope(self, raw=None):
        raw = wire(self.document) if raw is None else raw
        # Independent framing: do not use the implementation under test to sign.
        signing_bytes = (
            b"DSSEv1 51 application/vnd.aethron.capability-passport.v1+json "
            + str(len(raw)).encode("ascii")
            + b" "
            + raw
        )
        return wire(
            {
                "payloadType": passports.PAYLOAD_TYPE,
                "payload": b64(raw),
                "signatures": [
                    {"keyid": self.key_id, "sig": b64(self.private.sign(signing_bytes))}
                ],
            }
        )

    def verify(self, envelope=None, **kwargs):
        arguments = {
            "now_s": 1500,
            "minimum_time_s": 1400,
            "minimum_policy_revision": 3,
            "expected_subject_sha256": "a" * 64,
        }
        arguments.update(kwargs)
        return passports.verify(
            self.envelope() if envelope is None else envelope, wire(self.policy), **arguments
        )

    def assert_rejected(self, **kwargs):
        result = self.verify(**kwargs)
        self.assertEqual(result.status, "rejected")
        self.assertFalse(result.motion_authority)
        self.assertFalse(result.evidence_verified)
        self.assertIsNone(result.payload_sha256)
        self.assertIsNone(result.policy_revision)
        self.assertIsNone(result.expires_at)
        return result

    def test_revocation_rejection_does_not_persist_the_new_policy_floor(self):
        original_policy = copy.deepcopy(self.policy)
        envelope = self.envelope()
        self.assertEqual(self.verify(envelope).status, "authenticated")
        self.policy["revision"] = 4
        self.policy["revoked_passports"] = [self.document["passport_id"]]
        rejected = self.verify(envelope)
        self.assertEqual((rejected.status, rejected.reason), ("rejected", "revoked"))
        self.assertIsNone(rejected.policy_revision)
        self.assertIsNone(rejected.payload_sha256)
        self.assertIsNone(rejected.expires_at)
        # Model a caller restoring its old snapshot/floor. No disk or restart is tested.
        self.policy = original_policy
        replayed = self.verify(envelope)
        self.assertEqual((replayed.status, replayed.policy_revision), ("authenticated", 3))
        # Independently retained configuration state prevents that rollback.
        protected = self.verify(envelope, minimum_policy_revision=4)
        self.assertEqual((protected.status, protected.reason), ("rejected", "policy_rollback"))
        self.assertIsNone(protected.policy_revision)
        self.assertIsNone(protected.payload_sha256)
        self.assertIsNone(protected.expires_at)
        for result in (rejected, replayed, protected):
            self.assertIs(result.motion_authority, False)
            self.assertIs(result.evidence_verified, False)

    def test_expiry_rejection_does_not_persist_a_trusted_time_floor(self):
        envelope = self.envelope()
        self.assertEqual(self.verify(envelope, now_s=1500).status, "authenticated")
        expired = self.verify(envelope, now_s=2000)
        self.assertEqual((expired.status, expired.reason), ("rejected", "passport_not_current"))
        self.assertIsNone(expired.policy_revision)
        self.assertIsNone(expired.payload_sha256)
        self.assertIsNone(expired.expires_at)
        # Saving time only after successful authentication misses the trusted 2000 sample.
        rewound = self.verify(envelope, now_s=1500, minimum_time_s=1500)
        self.assertEqual(rewound.status, "authenticated")
        protected = self.verify(envelope, now_s=1500, minimum_time_s=2000)
        self.assertEqual((protected.status, protected.reason), ("rejected", "time_rollback"))
        self.assertIsNone(protected.policy_revision)
        self.assertIsNone(protected.payload_sha256)
        self.assertIsNone(protected.expires_at)
        for result in (expired, rewound, protected):
            self.assertIs(result.motion_authority, False)
            self.assertIs(result.evidence_verified, False)

    def test_unselected_key_metadata_is_not_ignored(self):
        other_public = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32).public_key()
        other_bytes = other_public.public_bytes(Encoding.Raw, PublicFormat.Raw)
        other = copy.deepcopy(self.policy["keys"][0])
        other.update(public_key=other_bytes.hex(), key_id=hashlib.sha256(other_bytes).hexdigest())
        self.policy["keys"].append(other)
        self.assertEqual(self.verify().status, "authenticated")
        for field, value in (
            ("issuer", "invalid/alias"),
            ("not_before", True),
            ("expires_at", other["not_before"]),
            ("capabilities", ["unknown"]),
            ("key_id", "0" * 64),
        ):
            with self.subTest(field=field):
                original = other[field]
                other[field] = value
                self.assertEqual(self.assert_rejected().reason, "invalid_input")
                other[field] = original

    def test_policy_expiry_caps_result_and_requires_reverification(self):
        self.policy["expires_at"] = 1600
        self.policy["keys"][0].update(not_before=1000, expires_at=2000)
        first = self.verify(now_s=1599)
        self.assertEqual(first.status, "authenticated")
        self.assertEqual(first.expires_at, 1600)
        self.assertEqual(self.assert_rejected(now_s=1600).reason, "policy_not_current")
        self.policy["expires_at"] = 1601
        self.assertEqual(self.verify(now_s=1600).status, "authenticated")

    def test_revocation_is_rechecked_after_success(self):
        envelope = self.envelope()
        self.assertEqual(self.verify(envelope=envelope).status, "authenticated")
        for field, identifier in (
            ("revoked_keys", self.key_id),
            ("revoked_passports", self.document["passport_id"]),
            ("revoked_evidence", self.document["evidence"][1]["sha256"]),
        ):
            with self.subTest(field=field):
                self.policy[field] = [identifier]
                self.assertEqual(self.assert_rejected(envelope=envelope).reason, "revoked")
                self.policy[field] = []

    def test_unsupported_crypto_rejects_without_authentication_metadata(self):
        from cryptography.exceptions import UnsupportedAlgorithm

        with patch("cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PublicKey") as backend:
            backend.from_public_bytes.side_effect = UnsupportedAlgorithm("fixture unavailable")
            self.assertEqual(self.assert_rejected().reason, "crypto_unavailable")
            backend.from_public_bytes.side_effect = None
            backend.from_public_bytes.return_value.verify.side_effect = UnsupportedAlgorithm(
                "fixture unavailable"
            )
            self.assertEqual(self.assert_rejected().reason, "crypto_unavailable")

    def test_real_signature_authenticates_only_statement(self):
        result = self.verify()
        self.assertEqual(result.status, "authenticated")
        self.assertFalse(result.motion_authority)
        self.assertFalse(result.evidence_verified)
        self.assertEqual(result.payload_sha256, hashlib.sha256(wire(self.document)).hexdigest())
        self.assertEqual(result.policy_revision, 3)
        self.assertEqual(result.expires_at, 2000)
        with self.assertRaises(AttributeError):
            result.motion_authority = True

    def test_half_open_time_boundaries_and_rollback(self):
        self.assertEqual(self.verify(now_s=1000, minimum_time_s=900).status, "authenticated")
        for now in (999, 2000, 2100, True, 1.0, -1, 2**53):
            self.assert_rejected(now_s=now, minimum_time_s=0)
        self.assert_rejected(now_s=1399)
        for floor in (4, True, 0, 2**53):
            self.assert_rejected(minimum_policy_revision=floor)
        for floor in (True, -1, 2**53):
            self.assert_rejected(minimum_time_s=floor)

    def test_policy_freshness_and_whole_key_interval(self):
        for field, value in (
            ("issued_at", 1501),
            ("expires_at", 1500),
            ("expires_at", 4501),
            ("revision", True),
        ):
            with self.subTest(field=field):
                old = self.policy[field]
                self.policy[field] = value
                self.assert_rejected()
                self.policy[field] = old
        for field, value in (("not_before", 1001), ("expires_at", 1999)):
            old = self.policy["keys"][0][field]
            self.policy["keys"][0][field] = value
            self.assert_rejected()
            self.policy["keys"][0][field] = old

    def test_subject_issuer_key_and_capability_scope(self):
        self.assert_rejected(expected_subject_sha256="d" * 64)
        self.document["issuer"] = "other-publisher"
        self.assert_rejected()
        self.document = payload()
        self.policy["keys"][0]["capabilities"] = ["presence.coarse.v2"]
        self.assert_rejected()
        self.policy["keys"][0]["public_key"] = "0" * 64
        self.assert_rejected()

    def test_revoked_passport_key_and_failed_evidence(self):
        for field, value in (
            ("revoked_passports", "fixture-statement-1"),
            ("revoked_keys", self.key_id),
            ("revoked_evidence", "c" * 64),
        ):
            self.policy[field] = [value]
            self.assert_rejected()
            self.policy[field] = []

    def test_tampering_noncanonical_and_malformed_envelopes(self):
        original = json.loads(self.envelope())
        altered_payload = payload()
        altered_payload["passport_id"] = "tampered"
        cases = []
        for field, value in (
            ("payloadType", "application/json"),
            ("payload", b64(wire(altered_payload))),
            ("payload", "!"),
            ("payload", original["payload"] + "="),
            ("signatures", []),
            ("signatures", original["signatures"] * 2),
        ):
            doc = copy.deepcopy(original)
            doc[field] = value
            cases.append(wire(doc))
        for field, value in (
            ("keyid", "0" * 64),
            ("sig", b64(b"\0" * 64)),
            ("sig", b64(b"\0" * 63)),
            ("algorithm", "none"),
        ):
            doc = copy.deepcopy(original)
            doc["signatures"][0][field] = value
            cases.append(wire(doc))
        cases.append(self.envelope(json.dumps(payload(), indent=2).encode()))
        cases += [b"{}", b"null", b"[" * 9, b" " * 65537, None, "string"]
        for raw in cases:
            with self.subTest(raw=str(raw)[:80]):
                # None is a helper default; call API directly for wrong types below.
                if raw is not None:
                    self.assert_rejected(envelope=raw)

    def test_policy_is_closed_bounded_and_validates_all_keys(self):
        original = copy.deepcopy(self.policy)
        for field, value in (
            ("extra", True),
            ("keys", []),
            ("keys", self.policy["keys"] * 2),
            ("revoked_keys", [self.key_id] * 2),
            ("revoked_passports", ["bad/id"]),
            ("revoked_evidence", ["a" * 64] * 257),
        ):
            self.policy[field] = value
            self.assert_rejected()
            self.policy = copy.deepcopy(original)

    def test_signed_authority_escalation_still_rejects(self):
        for field, value in (("motion_authority", True), ("assurance", "certified")):
            self.document[field] = value
            self.assert_rejected()
            self.document = payload()

    def test_scalar_confusion_never_escapes_or_authenticates(self):
        for field in payload():
            for value in (None, [], {}, True, 1.5):
                self.document = payload()
                self.document[field] = value
                with self.subTest(field=field, value=value):
                    self.assert_rejected()
        self.document = payload()
        for raw in (None, "{}", bytearray(b"{}"), memoryview(b"{}")):
            result = passports.verify(
                raw,
                wire(self.policy),
                now_s=1500,
                minimum_time_s=1400,
                minimum_policy_revision=3,
                expected_subject_sha256="a" * 64,
            )
            self.assertEqual(result.status, "rejected")

    def test_seeded_envelope_and_policy_mutations_are_bounded(self):
        rng = random.Random(1602)
        for _ in range(128):
            raw = bytearray(self.envelope())
            raw[rng.randrange(len(raw))] = rng.randrange(256)
            result = self.verify(envelope=bytes(raw))
            self.assertIn(result.status, {"authenticated", "rejected"})
            self.assertFalse(result.motion_authority)
            self.assertFalse(result.evidence_verified)
            raw_policy = bytearray(wire(self.policy))
            raw_policy[rng.randrange(len(raw_policy))] = rng.randrange(256)
            result = passports.verify(
                self.envelope(),
                bytes(raw_policy),
                now_s=1500,
                minimum_time_s=1400,
                minimum_policy_revision=3,
                expected_subject_sha256="a" * 64,
            )
            self.assertIn(result.status, {"authenticated", "rejected"})
            self.assertFalse(result.motion_authority)

    def test_portable_golden_and_negative_fixtures(self):
        root = Path(__file__).resolve().parents[1] / "examples/passports"
        vectors = json.loads((root / "vectors.json").read_bytes())
        self.assertEqual(vectors["canonical_payload"].encode(), wire(payload()))
        self.assertEqual(vectors["pae_hex"], passports.pae(wire(payload())).hex())
        self.assertEqual(vectors["payload_sha256"], hashlib.sha256(wire(payload())).hexdigest())
        for case in vectors["cases"]:
            result = passports.verify(
                case["envelope"].encode(),
                case["policy"].encode(),
                **case["arguments"],
            )
            with self.subTest(case=case["name"]):
                self.assertEqual(result.status, case["status"])
                self.assertEqual(result.reason, case["reason"])
                self.assertFalse(result.motion_authority)
                self.assertFalse(result.evidence_verified)


if __name__ == "__main__":
    unittest.main()
