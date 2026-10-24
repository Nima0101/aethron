"""Bounded offline input binding and revalidation; no execution authority."""

import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Optional, Tuple

from .interop_tasks import validate_task
from .passport_evidence import EvidenceReference, verify_evidence
from .passports import verify


@dataclass(frozen=True)
class BundleVerification:
    status: str
    reason: str
    task_sha256: Optional[str] = None
    passport_sha256: Optional[str] = None
    policy_revision: Optional[int] = None
    expires_at: Optional[int] = None
    evidence: Tuple[EvidenceReference, ...] = ()
    execution_authority: bool = field(default=False, init=False)
    motion_authority: bool = field(default=False, init=False)
    evidence_verified: bool = field(default=False, init=False)


def verify_task_bundle(
    task: bytes,
    envelope: bytes,
    policy: bytes,
    evidence: Tuple[bytes, ...],
    *,
    expected_task_sha256: str,
    expected_subject_sha256: str,
    now_s: int,
    minimum_time_s: int,
    minimum_policy_revision: int,
) -> BundleVerification:
    """Bind exact snapshots, then revalidate current signatures and trust offline."""
    if any(type(raw) is not bytes or len(raw) > 65536 for raw in (task, envelope, policy)):
        return BundleVerification("rejected", "invalid_bundle")
    if type(evidence) is not tuple or len(evidence) > 16:
        return BundleVerification("rejected", "invalid_bundle")
    if any(type(blob) is not bytes or len(blob) > 65536 for blob in evidence):
        return BundleVerification("rejected", "invalid_bundle")
    admitted = validate_task(
        task,
        expected_task_sha256=expected_task_sha256,
        expected_subject_sha256=expected_subject_sha256,
        now_s=now_s,
        minimum_time_s=minimum_time_s,
    )
    if admitted.status != "validated":
        return BundleVerification("rejected", "task_rejected")
    try:
        # The public task verifier validated these same immutable canonical bytes.
        description = json.loads(task.decode("utf-8"))
        if sum(map(len, evidence)) > description["max_evidence_bytes"]:
            return BundleVerification("rejected", "evidence_budget")
        if (
            sha256(envelope).hexdigest() != description["passport_sha256"]
            or sha256(policy).hexdigest() != description["policy_sha256"]
        ):
            return BundleVerification("rejected", "input_mismatch")
        digests = tuple(sha256(blob).hexdigest() for blob in evidence)
        if len(set(digests)) != len(digests) or set(digests) != set(description["evidence_sha256"]):
            return BundleVerification("rejected", "evidence_mismatch")
        arguments = {
            "now_s": now_s,
            "minimum_time_s": minimum_time_s,
            "minimum_policy_revision": minimum_policy_revision,
            "expected_subject_sha256": expected_subject_sha256,
        }
        if description["kind"] == "passport.verify.v1":
            proof = verify(envelope, policy, **arguments)
            if proof.status != "authenticated":
                return BundleVerification("rejected", "passport_rejected")
            passport_digest, references, reason = proof.payload_sha256, (), "passport_authenticated"
        else:
            proof = verify_evidence(envelope, policy, evidence, **arguments)
            if proof.status != "bound":
                return BundleVerification("rejected", "passport_rejected")
            passport_digest, references, reason = (
                proof.passport_sha256,
                proof.evidence,
                "evidence_bound",
            )
        return BundleVerification(
            "bound",
            reason,
            admitted.task_sha256,
            passport_digest,
            proof.policy_revision,
            min(admitted.expires_at, proof.expires_at),
            references,
        )
    except (ValueError, TypeError, KeyError, RecursionError):
        return BundleVerification("rejected", "invalid_bundle")
