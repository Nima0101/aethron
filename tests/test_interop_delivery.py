"""Compose the real inbox and federation boundaries with synthetic offline artifacts."""

import json
import unittest
from pathlib import Path

from aethron.interop_federation import verify_federated_bundle
from aethron.interop_inbox import BoundedInbox

VECTORS = Path(__file__).resolve().parents[1] / "examples/interop/federation-vectors-v1.json"


class DeliveryConformanceTests(unittest.TestCase):
    def setUp(self):
        self.cases = {case["name"]: case for case in json.loads(VECTORS.read_bytes())["cases"]}
        self.valid = self.cases["direct-peer-retains-negative-evidence"]
        self.inbox = BoundedInbox()
        self.addCleanup(self.inbox.close)

    def verify(self, case, envelope, **changes):
        return verify_federated_bundle(
            case["federation"].encode(),
            case["task"].encode(),
            envelope,
            case["policy"].encode(),
            tuple(bytes.fromhex(value) for value in case["evidence_hex"]),
            **dict(case["arguments"], **changes),
        )

    def queue(self):
        envelope = self.valid["envelope"].encode()
        result = self.inbox.put("peer-software", envelope, now_ms=1000, expires_at_ms=61000)
        self.assertEqual(result.status, "queued")
        self.assertIsNone(result.payload)
        self.assert_no_authority(result)
        return envelope

    def assert_no_authority(self, result):
        for name in ("execution_authority", "motion_authority", "evidence_verified"):
            self.assertIs(getattr(result, name), False)

    def assert_rejected(self, result, reason):
        self.assertEqual((result.status, result.reason), ("rejected", reason))
        for name in (
            "task_sha256",
            "passport_sha256",
            "federation_sha256",
            "federation_revision",
            "policy_revision",
            "expires_at",
        ):
            self.assertIsNone(getattr(result, name))
        self.assertEqual(result.evidence, ())
        self.assert_no_authority(result)

    def test_queue_lifetime_cannot_extend_federation_validity(self):
        envelope = self.queue()
        before = self.verify(self.valid, envelope, now_s=1599)
        self.assertEqual((before.status, before.expires_at), ("bound", 1600))
        delivered = self.inbox.take(now_ms=2000)
        self.assertEqual(delivered.payload, envelope)
        self.assertEqual(
            (delivered.status, delivered.reason), ("dequeued", "requires_verification")
        )
        self.assert_no_authority(delivered)
        self.assert_rejected(
            self.verify(self.valid, delivered.payload, now_s=1600), "federation_not_current"
        )
        # Two caller-provided clock domains: the inbox cannot infer wall-clock validity.
        self.assertEqual(before.status, "bound")

    def test_current_revocation_rejects_previously_queued_envelope(self):
        envelope = self.queue()
        before = self.verify(self.valid, envelope)
        self.assertEqual(before.status, "bound")
        self.assertEqual(
            [item.outcome for item in before.evidence], ["passed", "failed", "unknown"]
        )
        revoked = self.cases["repinned-revoked-negative-evidence"]
        self.assertEqual(revoked["envelope"].encode(), envelope)
        delivered = self.inbox.take(now_ms=2000)
        self.assertEqual(delivered.payload, envelope)
        self.assert_rejected(self.verify(revoked, delivered.payload), "bundle_rejected")
        # This is retained negative evidence: stale caller configuration still authenticates.
        self.assertEqual(self.verify(self.valid, delivered.payload).status, "bound")

    def test_current_revision_floor_rejects_queued_old_snapshot(self):
        envelope = self.queue()
        self.assertEqual(self.verify(self.valid, envelope).status, "bound")
        delivered = self.inbox.take(now_ms=2000)
        self.assert_rejected(
            self.verify(self.valid, delivered.payload, minimum_federation_revision=6),
            "federation_rollback",
        )

    def test_close_prevents_delivery_but_cannot_revoke_a_returned_copy(self):
        self.queue()
        delivered = self.inbox.take(now_ms=2000)
        queued = self.inbox.put(
            "peer-software", delivered.payload, now_ms=2000, expires_at_ms=61000
        )
        self.assertEqual(queued.status, "queued")
        self.inbox.close()
        closed = self.inbox.take(now_ms=2001)
        self.assertEqual(
            (closed.status, closed.reason, closed.items, closed.payload_bytes),
            ("rejected", "closed", 0, 0),
        )
        self.assertIsNone(closed.payload)
        self.assert_no_authority(closed)
        self.assertEqual(self.verify(self.valid, delivered.payload).status, "bound")


if __name__ == "__main__":
    unittest.main()
