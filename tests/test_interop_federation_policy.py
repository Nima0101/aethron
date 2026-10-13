"""Pinned snapshot admission must not depend on successful bundle authentication."""

import copy
import dataclasses
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron import interop_federation as federation

ROOT = Path(__file__).resolve().parents[1]


def wire(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


class FederationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.cases = json.loads(
            (ROOT / "examples/interop/federation-policy-vectors-v1.json").read_bytes()
        )["cases"]
        self.raw = self.cases[0]["federation"].encode()
        self.arguments = self.cases[0]["arguments"]

    def check(self, raw=None, **changes):
        return federation.validate_pinned_federation(
            self.raw if raw is None else raw, **dict(self.arguments, **changes)
        )

    def rejected(self, result, reason="invalid_federation"):
        self.assertEqual(
            dataclasses.asdict(result),
            {
                "status": "rejected",
                "reason": reason,
                "federation_sha256": None,
                "federation_revision": None,
                "expires_at": None,
                "execution_authority": False,
                "motion_authority": False,
                "evidence_verified": False,
            },
        )

    def test_portable_admission_cases_and_complete_metadata(self):
        self.assertEqual(
            [c["name"] for c in self.cases],
            [
                "deny-all",
                "one-peer",
                "wrong-pin",
                "wrong-domain",
                "revision-rollback",
                "time-rollback",
                "expired",
                "future",
                "noncanonical",
                "malformed-row",
            ],
        )
        for case in self.cases:
            with self.subTest(case=case["name"]):
                result = federation.validate_pinned_federation(
                    case["federation"].encode(), **case["arguments"]
                )
                if case["status"] == "validated":
                    self.assertEqual(
                        dataclasses.asdict(result),
                        {
                            "status": "validated",
                            "reason": "federation_matches",
                            "federation_sha256": hashlib.sha256(
                                case["federation"].encode()
                            ).hexdigest(),
                            "federation_revision": 5,
                            "expires_at": 1600,
                            "execution_authority": False,
                            "motion_authority": False,
                            "evidence_verified": False,
                        },
                    )
                    with self.assertRaises(dataclasses.FrozenInstanceError):
                        result.federation_revision = 0
                else:
                    self.rejected(result, case["reason"])

    def test_deny_all_validates_without_invoking_bundle_verifier(self):
        with patch.object(federation, "verify_task_bundle", side_effect=AssertionError("bundle")):
            self.assertEqual(self.check().status, "validated")
            # The same valid table still rejects every peer through the existing API.
            denied = federation.verify_federated_bundle(
                self.raw,
                b"",
                b"",
                b"",
                (),
                **self.arguments,
                remote_domain="peer-software",
                expected_task_sha256="a" * 64,
                expected_subject_sha256="b" * 64,
                minimum_policy_revision=1,
            )
        self.assertEqual((denied.status, denied.reason), ("rejected", "untrusted_peer"))
        self.assertIsNone(denied.federation_revision)

    def test_existing_bundle_snapshot_rejection_reasons_are_preserved(self):
        for case in self.cases:
            if case["status"] != "rejected":
                continue
            with self.subTest(case=case["name"]):
                result = federation.verify_federated_bundle(
                    case["federation"].encode(),
                    b"",
                    b"",
                    b"",
                    (),
                    **case["arguments"],
                    remote_domain="peer-software",
                    expected_task_sha256="a" * 64,
                    expected_subject_sha256="b" * 64,
                    minimum_policy_revision=1,
                )
                self.assertEqual((result.status, result.reason), ("rejected", case["reason"]))
                self.assertIsNone(result.federation_revision)
                self.assertIsNone(result.federation_sha256)
                self.assertIsNone(result.expires_at)

    def test_half_open_time_interval_and_independent_revision_floor(self):
        for now in (1400, 1599):
            self.assertEqual(self.check(now_s=now).status, "validated")
        self.assertEqual(self.check(minimum_federation_revision=1).status, "validated")
        for changes, reason in (
            ({"now_s": 1399, "minimum_time_s": 0}, "federation_not_current"),
            ({"now_s": 1600}, "federation_not_current"),
            ({"minimum_time_s": 1501}, "federation_rollback"),
            ({"minimum_federation_revision": 6}, "federation_rollback"),
        ):
            self.rejected(self.check(**changes), reason)

    def test_invalid_caller_values_never_return_metadata(self):
        for field in ("now_s", "minimum_time_s", "minimum_federation_revision"):
            for value in (True, 1.0, -1, 2**53, "5", None):
                with self.subTest(field=field, value=value):
                    self.rejected(self.check(**{field: value}))
        self.rejected(self.check(minimum_federation_revision=0))
        for field, values in (
            ("local_domain", ("", "bad/alias", "x\n", None)),
            ("expected_federation_sha256", ("a" * 63, "A" * 64, None)),
        ):
            for value in values:
                self.rejected(self.check(**{field: value}))

    def test_all_peer_rows_and_capacity_are_validated(self):
        doc = json.loads(self.cases[1]["federation"])
        peer = doc["peers"][0]
        doc["peers"] = [dict(peer, remote_domain="peer-" + str(i)) for i in range(16)]
        raw = wire(doc)
        self.assertEqual(
            self.check(raw, expected_federation_sha256=hashlib.sha256(raw).hexdigest()).status,
            "validated",
        )
        for field, value in (
            ("issuers", []),
            ("capabilities", ["unknown"]),
            ("policy_sha256", "f" * 63),
            ("remote_domain", "local-software"),
            ("remote_domain", "peer-0"),
        ):
            changed = copy.deepcopy(doc)
            changed["peers"][-1][field] = value
            raw = wire(changed)
            self.rejected(
                self.check(raw, expected_federation_sha256=hashlib.sha256(raw).hexdigest())
            )
        doc["peers"].append(dict(peer, remote_domain="peer-16"))
        raw = wire(doc)
        self.rejected(self.check(raw, expected_federation_sha256=hashlib.sha256(raw).hexdigest()))

    def test_lexical_canonical_and_byte_bounds_precede_hashing(self):
        class DerivedBytes(bytes):
            pass

        invalid = (
            bytearray(self.raw),
            memoryview(self.raw),
            DerivedBytes(self.raw),
            self.raw.decode(),
            b"x" * 65537,
            b"[" * 9 + b"]" * 9,
            self.raw + b"\n",
            self.raw.replace(b'"revision":5', b'"revision":5.0'),
            self.raw.replace(b'"revision":5', b'"revision":5,"revision":5'),
            self.raw.replace(b'"revision":5', b'"revision":' + b"9" * 1000),
            self.raw.decode().encode("utf-16"),
            b"\xff",
            b"null",
        )
        with patch.object(federation, "sha256", side_effect=AssertionError("hash reached")):
            for raw in invalid:
                with self.subTest(type=type(raw).__name__):
                    self.rejected(self.check(raw))

    def test_saved_result_does_not_persist_floors_or_detect_equivocation(self):
        accepted = self.check()
        self.rejected(self.check(minimum_federation_revision=6), "federation_rollback")
        self.assertEqual(self.check().status, "validated")
        changed = json.loads(self.raw)
        changed["expires_at"] += 1
        raw = wire(changed)
        self.rejected(self.check(raw), "federation_mismatch")
        other = self.check(raw, expected_federation_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual(other.status, "validated")
        self.assertEqual(accepted.federation_revision, other.federation_revision)
        self.assertNotEqual(accepted.federation_sha256, other.federation_sha256)
