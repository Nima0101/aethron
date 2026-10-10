"""Bind task, envelope, policy and evidence without granting authority."""

import dataclasses
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import test_passport_evidence as fixtures

from aethron import interop_bundles


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


@unittest.skipIf(fixtures.fixtures.Ed25519PrivateKey is None, "install passports extra")
class TaskBundleTests(unittest.TestCase):
    def test_portable_vectors(self):
        path = Path(__file__).resolve().parents[1] / "examples/interop/bundle-vectors-v1.json"
        for case in json.loads(path.read_bytes())["cases"]:
            result = interop_bundles.verify_task_bundle(
                case["task"].encode(),
                case["envelope"].encode(),
                case["policy"].encode(),
                tuple(bytes.fromhex(value) for value in case["evidence_hex"]),
                **case["arguments"],
            )
            self.assertEqual(
                (result.status, result.reason), (case["status"], case["reason"]), case["name"]
            )
            self.assertEqual([value.outcome for value in result.evidence], case["outcomes"])
            self.assertIs(result.motion_authority, False)
            self.assertIs(result.execution_authority, False)

    def setUp(self):
        self.fixture = fixtures.EvidenceBindingTests()
        self.fixture.setUp()
        self.envelope = self.fixture.signer.envelope()
        self.policy = fixtures.fixtures.wire(self.fixture.signer.policy)
        self.blobs = self.fixture.blobs
        self.task = {
            "version": 1,
            "task_id": "fixture-bundle",
            "kind": "evidence.bind.v1",
            "subject_sha256": "a" * 64,
            "passport_sha256": digest(self.envelope),
            "policy_sha256": digest(self.policy),
            "evidence_sha256": [digest(blob) for blob in self.blobs],
            "issued_at": 1400,
            "expires_at": 1700,
            "max_evidence_bytes": sum(map(len, self.blobs)),
            "motion_authority": False,
        }

    def check(self, **changes):
        raw = fixtures.fixtures.wire(self.task)
        arguments = dict(self.fixture.arguments, expected_task_sha256=digest(raw))
        arguments.update(task=raw, envelope=self.envelope, policy=self.policy, evidence=self.blobs)
        arguments.update(changes)
        return interop_bundles.verify_task_bundle(**arguments)

    def test_authenticated_binding_preserves_all_outcomes_and_earliest_expiry(self):
        result = self.check()
        self.assertEqual((result.status, result.reason), ("bound", "evidence_bound"))
        self.assertEqual(
            [item.outcome for item in result.evidence], ["passed", "failed", "unknown"]
        )
        self.assertEqual(result.expires_at, 1700)
        self.assertEqual(result.policy_revision, 3)
        self.assertEqual(result, self.check(evidence=tuple(reversed(self.blobs))))
        for key in ("execution_authority", "motion_authority", "evidence_verified"):
            self.assertIs(dataclasses.asdict(result)[key], False)
        self.assertNotIn("synthetic negative report", repr(result))

    def test_input_pins_and_evidence_set_fail_closed(self):
        for changes in (
            {"envelope": self.envelope + b" "},
            {"policy": self.policy + b" "},
            {"evidence": self.blobs[:-1]},
            {"evidence": self.blobs + (b"extra",)},
            {"evidence": self.blobs[:-1] + (b"replaced",)},
            {"evidence": self.blobs + (self.blobs[0],)},
        ):
            with self.subTest(changes=changes):
                result = self.check(**changes)
                self.assertEqual(result.status, "rejected")
                self.assertEqual(result.evidence, ())
                self.assertIsNone(result.task_sha256)

    def test_budget_and_unreferenced_signed_evidence(self):
        self.task["max_evidence_bytes"] -= 1
        self.assertEqual(self.check().reason, "evidence_budget")
        self.task["max_evidence_bytes"] += 1
        self.task["evidence_sha256"] = self.task["evidence_sha256"][:-1]
        # Caller even pins a task omitting one assertion; signed evidence still rules.
        self.assertEqual(self.check(evidence=self.blobs[:-1]).reason, "passport_rejected")

    def test_bounds_before_any_hash_or_verifier(self):
        class Blob(bytes):
            pass

        raw = fixtures.fixtures.wire(self.task)
        args = dict(
            self.fixture.arguments,
            expected_task_sha256=digest(raw),
            task=raw,
            envelope=self.envelope,
            policy=self.policy,
            evidence=self.blobs,
        )
        with (
            patch.object(
                interop_bundles, "validate_task", side_effect=AssertionError("validation")
            ),
            patch.object(interop_bundles, "sha256", side_effect=AssertionError("hash")),
        ):
            for change in (
                {"task": b" " * 65537},
                {"envelope": b" " * 65537},
                {"policy": bytearray(self.policy)},
                {"evidence": list(self.blobs)},
                {"evidence": (Blob(b"a"),)},
                {"evidence": (b"a",) * 17},
                {"evidence": (b"a" * 65537,)},
            ):
                self.assertEqual(
                    interop_bundles.verify_task_bundle(**dict(args, **change)).reason,
                    "invalid_bundle",
                )

    def test_time_revision_and_revocation_rechecked(self):
        self.assertEqual(self.check(now_s=1700).reason, "task_rejected")
        self.assertEqual(self.check(minimum_time_s=1501).reason, "task_rejected")
        self.assertEqual(self.check(minimum_policy_revision=4).reason, "passport_rejected")
        trust = json.loads(self.policy)
        trust["revoked_evidence"] = [self.task["evidence_sha256"][1]]
        self.policy = fixtures.fixtures.wire(trust)
        self.task["policy_sha256"] = digest(self.policy)
        self.assertEqual(self.check().reason, "passport_rejected")

    def test_policy_expiry_caps_bundle_expiry(self):
        trust = json.loads(self.policy)
        trust["expires_at"] = 1550
        self.policy = fixtures.fixtures.wire(trust)
        self.task["policy_sha256"] = digest(self.policy)
        self.assertEqual(self.check().expires_at, 1550)
        self.assertEqual(self.check(now_s=1550).reason, "passport_rejected")

    def test_passport_only_cannot_accept_evidence(self):
        self.task.update(kind="passport.verify.v1", evidence_sha256=[], max_evidence_bytes=0)
        result = self.check(evidence=())
        self.assertEqual((result.status, result.reason), ("bound", "passport_authenticated"))
        self.assertEqual(result.evidence, ())
        self.assertEqual(self.check().status, "rejected")


if __name__ == "__main__":
    unittest.main()
