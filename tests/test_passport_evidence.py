"""Bound evidence content without upgrading assertions to qualified evidence."""

import dataclasses
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_passports as fixtures

from aethron import passport_evidence


@unittest.skipIf(fixtures.Ed25519PrivateKey is None, "install passports extra for signature tests")
class EvidenceBindingTests(unittest.TestCase):
    def setUp(self):
        self.signer = fixtures.PassportVerificationTests()
        self.signer.setUp()
        self.blobs = (b"abc", b"synthetic negative report\n", b"unknown support\n")
        self.set_evidence(self.blobs)
        self.arguments = {
            "now_s": 1500,
            "minimum_time_s": 1400,
            "minimum_policy_revision": 3,
            "expected_subject_sha256": "a" * 64,
        }

    def set_evidence(self, blobs):
        refs = [hashlib.sha256(blob).hexdigest() for blob in blobs]
        self.signer.document["evidence"] = [
            {
                "sha256": digest,
                "kind": "synthetic",
                "outcome": ("passed", "failed", "unknown")[i % 3],
            }
            for i, digest in enumerate(refs)
        ]
        self.signer.document["capabilities"][0]["evidence_sha256"] = refs

    def verify(self, blobs=None, **kwargs):
        return passport_evidence.verify_evidence(
            self.signer.envelope(),
            fixtures.wire(self.signer.policy),
            self.blobs if blobs is None else blobs,
            **{**self.arguments, **kwargs},
        )

    def rejected(self, blobs=None, **kwargs):
        result = self.verify(blobs, **kwargs)
        self.assertEqual(result.status, "rejected")
        self.assertFalse(result.motion_authority)
        self.assertFalse(result.evidence_verified)
        self.assertEqual(result.evidence, ())
        self.assertIsNone(result.passport_sha256)
        self.assertIsNone(result.policy_revision)
        self.assertIsNone(result.expires_at)
        return result

    def test_exact_content_binds_and_preserves_negative_outcomes(self):
        result = self.verify()
        self.assertEqual(result.status, "bound")
        self.assertEqual(result.reason, "content_digests_match")
        self.assertEqual(
            result.evidence[0].sha256,
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )
        self.assertEqual(
            [item.outcome for item in result.evidence], ["passed", "failed", "unknown"]
        )
        self.assertEqual(result.policy_revision, 3)
        self.assertEqual(result.expires_at, 2000)
        self.assertEqual(result, self.verify(tuple(reversed(self.blobs))))
        self.assertFalse(dataclasses.asdict(result)["motion_authority"])
        self.assertFalse(dataclasses.asdict(result)["evidence_verified"])
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.evidence[0].outcome = "passed"
        self.assertNotIn("synthetic negative report", repr(result))

    def test_incomplete_extra_substituted_and_duplicate_content_rejected(self):
        for blobs in (
            self.blobs[:-1],
            self.blobs + (b"extra",),
            self.blobs[:-1] + (b"substituted",),
            self.blobs + (self.blobs[0],),
        ):
            with self.subTest(blobs=blobs):
                self.rejected(blobs)

    def test_every_signed_kind_and_outcome_preserves_reference_order(self):
        references = self.signer.document["evidence"]
        for reference, kind in zip(references, ("synthetic", "recorded", "external_unverified")):
            reference["kind"] = kind
        expected = tuple(dict(reference) for reference in references)
        # Both input ordering and signed ordering differ from the default fixture.
        references.reverse()
        result = self.verify(tuple(reversed(self.blobs)))
        self.assertEqual(result.status, "bound")
        self.assertEqual(
            tuple(dataclasses.asdict(reference) for reference in result.evidence),
            tuple(reversed(expected)),
        )
        self.assertFalse(result.motion_authority)
        self.assertFalse(result.evidence_verified)

    def test_entire_input_validated_before_crypto_or_content_hash(self):
        class BytesSubclass(bytes):
            pass

        class TupleSubclass(tuple):
            pass

        bad_inputs = [
            (),
            self.blobs * 6,
            (b"x" * 65537,),
            [b"abc"],
            "file:///private",
            (bytearray(b"abc"),),
            (memoryview(b"abc"),),
            (BytesSubclass(b"abc"),),
            TupleSubclass(self.blobs),
            iter(self.blobs),
            (b"abc", None),
        ]
        with patch.object(passport_evidence, "verify", side_effect=AssertionError("crypto")):
            with patch.object(passport_evidence, "sha256", side_effect=AssertionError("hashed")):
                for blobs in bad_inputs:
                    with self.subTest(kind=type(blobs)):
                        self.rejected(blobs)
                result = passport_evidence.verify_evidence(b"", b"", None, **self.arguments)
                self.assertEqual(result.status, "rejected")

    def test_maximum_input_and_empty_blob_are_supported_with_exact_digest(self):
        blobs = tuple(bytes([i]) * 65536 for i in range(16))
        self.set_evidence(blobs)
        self.assertEqual(self.verify(blobs).status, "bound")
        self.set_evidence((b"",))
        self.assertEqual(self.verify((b"",)).status, "bound")

    def test_invalid_passport_stops_before_content_hash(self):
        with patch.object(passport_evidence, "sha256", side_effect=AssertionError("hashed")):
            for arguments in (
                {"now_s": 2000},
                {"minimum_policy_revision": 4},
                {"minimum_time_s": 1501},
                {"expected_subject_sha256": "d" * 64},
            ):
                self.rejected(**arguments)
            self.signer.policy["revoked_evidence"] = [hashlib.sha256(self.blobs[1]).hexdigest()]
            self.rejected()
            self.signer.policy["revoked_evidence"] = []
            with patch.dict(
                "sys.modules", {"cryptography.hazmat.primitives.asymmetric.ed25519": None}
            ):
                self.rejected()

    def test_hash_backend_failure_returns_fixed_rejection(self):
        with patch.object(passport_evidence, "sha256", side_effect=ValueError("private content")):
            result = self.rejected()
        self.assertNotIn("private content", repr(result))

    def test_late_hash_failure_discards_all_partial_metadata(self):
        calls = 0

        def fail_last(blob):
            nonlocal calls
            calls += 1
            if calls == len(self.blobs):
                raise ValueError("private final report")
            return hashlib.sha256(blob)

        with patch.object(passport_evidence, "sha256", side_effect=fail_last):
            result = self.rejected()
        self.assertEqual(calls, len(self.blobs))
        self.assertEqual(result.reason, "invalid_evidence")
        self.assertNotIn("private final report", repr(result))

    def test_blob_claims_cannot_override_signed_outcome_or_authority(self):
        blob = b'{"outcome":"passed","evidence_verified":true,"motion_authority":true}'
        self.set_evidence((blob,))
        self.signer.document["evidence"][0]["outcome"] = "failed"
        result = self.verify((blob,))
        self.assertEqual(result.status, "bound")
        self.assertEqual(result.evidence[0].outcome, "failed")
        self.assertFalse(result.motion_authority)
        self.assertFalse(result.evidence_verified)
        self.assertNotIn(blob.decode(), repr(result))

    def test_tampered_signature_stops_before_content_hash(self):
        envelope = json.loads(self.signer.envelope())
        altered = dict(self.signer.document, passport_id="changed-after-signing")
        envelope["payload"] = fixtures.b64(fixtures.wire(altered))
        with patch.object(passport_evidence, "sha256", side_effect=AssertionError("hashed")):
            result = passport_evidence.verify_evidence(
                fixtures.wire(envelope),
                fixtures.wire(self.signer.policy),
                self.blobs,
                **self.arguments,
            )
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.reason, "passport_rejected")
        self.assertEqual(result.evidence, ())
        self.assertIsNone(result.passport_sha256)
        self.assertIsNone(result.policy_revision)
        self.assertIsNone(result.expires_at)
        self.assertFalse(result.motion_authority)
        self.assertFalse(result.evidence_verified)

    def test_portable_binding_vectors(self):
        path = Path(__file__).resolve().parents[1] / "examples/passports/evidence-vectors.json"
        vectors = json.loads(path.read_bytes())
        for case in vectors["cases"]:
            result = passport_evidence.verify_evidence(
                case["envelope"].encode(),
                case["policy"].encode(),
                tuple(bytes.fromhex(blob) for blob in case["evidence_hex"]),
                **case["arguments"],
            )
            with self.subTest(case=case["name"]):
                self.assertEqual(result.status, case["status"])
                self.assertEqual(result.reason, case["reason"])
                self.assertEqual([item.outcome for item in result.evidence], case["outcomes"])
                self.assertFalse(result.motion_authority)
                self.assertFalse(result.evidence_verified)


if __name__ == "__main__":
    unittest.main()
