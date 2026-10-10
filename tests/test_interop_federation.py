"""Direct software-domain trust cannot become transitive or confer authority."""

import copy
import dataclasses
import json
import unittest
from pathlib import Path

import test_interop_bundles as fixtures
import test_passports as passport_fixtures

from aethron import interop_federation


@unittest.skipIf(passport_fixtures.Ed25519PrivateKey is None, "install passports extra")
class FederationTests(unittest.TestCase):
    def test_portable_vectors(self):
        path = Path(__file__).resolve().parents[1] / "examples/interop/federation-vectors-v1.json"
        for case in json.loads(path.read_bytes())["cases"]:
            result = interop_federation.verify_federated_bundle(
                case["federation"].encode(),
                case["task"].encode(),
                case["envelope"].encode(),
                case["policy"].encode(),
                tuple(bytes.fromhex(value) for value in case["evidence_hex"]),
                **case["arguments"],
            )
            self.assertEqual(
                (result.status, result.reason), (case["status"], case["reason"]), case["name"]
            )
            self.assertEqual([item.outcome for item in result.evidence], case["outcomes"])
            self.assertIs(result.execution_authority, False)
            self.assertIs(result.motion_authority, False)

    def setUp(self):
        self.bundle = fixtures.TaskBundleTests()
        self.bundle.setUp()
        self.snapshot = {
            "version": 1,
            "revision": 5,
            "local_domain": "local-software",
            "issued_at": 1400,
            "expires_at": 1600,
            "peers": [
                {
                    "remote_domain": "peer-software",
                    "policy_sha256": fixtures.digest(self.bundle.policy),
                    "issuers": ["fixture-publisher"],
                    "capabilities": ["perception.direct.v3"],
                }
            ],
        }

    def arguments(self):
        task = passport_fixtures.wire(self.bundle.task)
        federation = passport_fixtures.wire(self.snapshot)
        return dict(
            self.bundle.fixture.arguments,
            task=task,
            envelope=self.bundle.envelope,
            policy=self.bundle.policy,
            evidence=self.bundle.blobs,
            expected_task_sha256=fixtures.digest(task),
            federation=federation,
            expected_federation_sha256=fixtures.digest(federation),
            local_domain="local-software",
            remote_domain="peer-software",
            minimum_federation_revision=5,
        )

    def check(self, **changes):
        return interop_federation.verify_federated_bundle(**dict(self.arguments(), **changes))

    def test_direct_scope_and_expiry_preserve_negatives(self):
        result = self.check()
        self.assertEqual(result.status, "bound")
        self.assertEqual(result.expires_at, 1600)
        self.assertEqual(result.federation_revision, 5)
        self.assertEqual(result.policy_revision, 3)
        self.assertEqual([x.outcome for x in result.evidence], ["passed", "failed", "unknown"])
        for key in ("execution_authority", "motion_authority", "evidence_verified"):
            self.assertIs(dataclasses.asdict(result)[key], False)

    def test_pins_domains_and_no_transitive_resolution(self):
        for change in (
            {"expected_federation_sha256": "f" * 64},
            {"local_domain": "other-local"},
            {"remote_domain": "peer-of-peer"},
        ):
            self.assertEqual(self.check(**change).status, "rejected")
        self.snapshot["peers"][0]["policy_sha256"] = "f" * 64
        self.assertEqual(self.check().reason, "peer_policy_mismatch")
        self.snapshot["peers"] = []
        self.assertEqual(self.check().reason, "untrusted_peer")

    def test_scope_cannot_expand(self):
        self.snapshot["peers"][0]["issuers"] = ["other-publisher"]
        self.assertEqual(self.check().reason, "peer_scope_mismatch")

    def test_every_signed_capability_requires_direct_scope(self):
        signer = self.bundle.fixture.signer
        signer.document["capabilities"].append(
            {
                "name": "presence.coarse.v2",
                "evidence_sha256": list(signer.document["capabilities"][0]["evidence_sha256"]),
            }
        )
        signer.policy["keys"][0]["capabilities"].append("presence.coarse.v2")
        self.bundle.envelope = signer.envelope()
        self.bundle.policy = passport_fixtures.wire(signer.policy)
        self.bundle.task["passport_sha256"] = fixtures.digest(self.bundle.envelope)
        self.bundle.task["policy_sha256"] = fixtures.digest(self.bundle.policy)
        self.snapshot["peers"][0]["policy_sha256"] = fixtures.digest(self.bundle.policy)
        self.assertEqual(self.check().reason, "peer_scope_mismatch")
        self.snapshot["peers"][0]["capabilities"].append("presence.coarse.v2")
        self.assertEqual(self.check().status, "bound")
        self.snapshot["peers"][0]["issuers"] = ["fixture-publisher"]
        self.snapshot["peers"][0]["capabilities"] = ["presence.coarse.v2"]
        self.assertEqual(self.check().reason, "peer_scope_mismatch")

    def test_current_time_and_separate_revision_floors(self):
        for change in (
            {"now_s": 1600},
            {"now_s": 1399, "minimum_time_s": 0},
            {"minimum_time_s": 1501},
            {"minimum_federation_revision": 6},
            {"minimum_policy_revision": 4},
        ):
            self.assertEqual(self.check(**change).status, "rejected")
        for value in (True, 1.0, 0, 2**53, "5"):
            self.assertEqual(
                self.check(minimum_federation_revision=value).reason, "invalid_federation"
            )

    def test_revoked_passport_cannot_be_rescoped_back_to_trust(self):
        policy = json.loads(self.bundle.policy)
        policy["revoked_evidence"] = [self.bundle.task["evidence_sha256"][1]]
        self.bundle.policy = passport_fixtures.wire(policy)
        digest = fixtures.digest(self.bundle.policy)
        self.bundle.task["policy_sha256"] = digest
        self.snapshot["peers"][0]["policy_sha256"] = digest
        result = self.check()
        self.assertEqual(result.reason, "bundle_rejected")
        self.assertEqual(result.evidence, ())
        self.assertIsNone(result.passport_sha256)

    def test_closed_bounded_canonical_policy(self):
        original = copy.deepcopy(self.snapshot)
        mutations = []
        for key, value in (
            ("version", True),
            ("revision", 0),
            ("expires_at", 5001),
            ("local_domain", "local\n"),
            ("delegation", True),
            ("peers", original["peers"] * 17),
        ):
            changed = copy.deepcopy(original)
            changed[key] = value
            mutations.append(changed)
        for key, value in (
            ("remote_domain", "local-software"),
            ("issuers", []),
            ("issuers", ["fixture-publisher"] * 2),
            ("capabilities", ["motion.follow"]),
            ("delegate", "peer-of-peer"),
        ):
            changed = copy.deepcopy(original)
            changed["peers"][0][key] = value
            mutations.append(changed)
        changed = copy.deepcopy(original)
        changed["peers"] *= 2
        mutations.append(changed)
        for changed in mutations:
            self.snapshot = changed
            self.assertEqual(self.check().reason, "invalid_federation")
        self.snapshot = original
        raw = passport_fixtures.wire(original)
        for invalid in (
            b" " * 65537,
            b"[" * 9,
            bytearray(raw),
            b"\xff",
            raw.replace(b'"version":1', b'"version":1,"version":1'),
            raw.replace(b'"version":1', b'"version":1e0'),
            json.dumps(original, indent=2).encode(),
        ):
            self.assertEqual(self.check(federation=invalid).reason, "invalid_federation")


if __name__ == "__main__":
    unittest.main()
