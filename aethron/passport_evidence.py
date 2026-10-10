"""Bind immutable local bytes to passport assertions without qualifying their truth."""

import base64
import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Optional, Tuple

from .passports import verify


@dataclass(frozen=True)
class EvidenceReference:
    sha256: str
    kind: str
    outcome: str


@dataclass(frozen=True)
class EvidenceBindingResult:
    status: str
    reason: str
    passport_sha256: Optional[str] = None
    policy_revision: Optional[int] = None
    expires_at: Optional[int] = None
    evidence: Tuple[EvidenceReference, ...] = ()
    motion_authority: bool = field(default=False, init=False)
    evidence_verified: bool = field(default=False, init=False)


def verify_evidence(
    envelope: bytes,
    policy: bytes,
    evidence: Tuple[bytes, ...],
    *,
    now_s: int,
    minimum_time_s: int,
    minimum_policy_revision: int,
    expected_subject_sha256: str,
) -> EvidenceBindingResult:
    """Reauthenticate v1, then match every signed digest to a bounded bytes snapshot.

    Callers supply trustworthy policy, clock/floors and expected software digest.
    Raw evidence is neither interpreted nor retained in the returned result.
    """
    if type(evidence) is not tuple or not 1 <= len(evidence) <= 16:
        return EvidenceBindingResult("rejected", "invalid_evidence")
    if any(type(blob) is not bytes or len(blob) > 65536 for blob in evidence):
        return EvidenceBindingResult("rejected", "invalid_evidence")
    authenticated = verify(
        envelope,
        policy,
        now_s=now_s,
        minimum_time_s=minimum_time_s,
        minimum_policy_revision=minimum_policy_revision,
        expected_subject_sha256=expected_subject_sha256,
    )
    if authenticated.status != "authenticated":
        return EvidenceBindingResult("rejected", "passport_rejected")
    try:
        # v1 has already checked these exact immutable bytes, including duplicates,
        # UTF-8, canonical encoding, byte/depth limits and closed schema. Re-decoding
        # here keeps the adapter on the public v1 API without retaining content in it.
        outer = json.loads(envelope.decode("utf-8"))
        statement = json.loads(base64.b64decode(outer["payload"], validate=True))
        actual = tuple(sha256(blob).hexdigest() for blob in evidence)
        if len(set(actual)) != len(actual):
            return EvidenceBindingResult("rejected", "duplicate_evidence")
        if set(actual) != {item["sha256"] for item in statement["evidence"]}:
            return EvidenceBindingResult("rejected", "evidence_set_mismatch")
        references = tuple(
            EvidenceReference(item["sha256"], item["kind"], item["outcome"])
            for item in statement["evidence"]
        )
        return EvidenceBindingResult(
            "bound",
            "content_digests_match",
            authenticated.payload_sha256,
            authenticated.policy_revision,
            authenticated.expires_at,
            references,
        )
    except (ValueError, TypeError, KeyError, RecursionError):
        return EvidenceBindingResult("rejected", "invalid_evidence")
