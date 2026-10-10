"""Direct pinned software-domain scope, never transitive trust or authority."""

import base64
import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Optional, Tuple

from .interop_bundles import verify_task_bundle
from .passport_evidence import EvidenceReference
from .passports import (
    _HEX,
    CAPABILITIES,
    _canonical,
    _integer,
    _interval,
    _list,
    _object,
    _parse,
    _require,
    _token,
    _unique_tokens,
)


def _snapshot(value):
    _object(value, "version revision local_domain issued_at expires_at peers")
    _integer(value["version"], 1)
    _require(value["version"] == 1)
    _integer(value["revision"], 1)
    _token(value["local_domain"])
    _interval(value["issued_at"], value["expires_at"], 3600)
    _list(value["peers"], 16, 0)
    peers = {}
    for peer in value["peers"]:
        _object(peer, "remote_domain policy_sha256 issuers capabilities")
        _token(peer["remote_domain"])
        _require(
            peer["remote_domain"] != value["local_domain"] and peer["remote_domain"] not in peers
        )
        _token(peer["policy_sha256"], _HEX)
        _unique_tokens(peer["issuers"], 16)
        _unique_tokens(peer["capabilities"], 3, allowed=CAPABILITIES)
        peers[peer["remote_domain"]] = peer
    return value, peers


@dataclass(frozen=True)
class FederationValidation:
    """Complete snapshot admission; neither peer acceptance nor authority."""

    status: str
    reason: str
    federation_sha256: Optional[str] = None
    federation_revision: Optional[int] = None
    expires_at: Optional[int] = None
    execution_authority: bool = field(default=False, init=False)
    motion_authority: bool = field(default=False, init=False)
    evidence_verified: bool = field(default=False, init=False)


def validate_pinned_federation(
    federation: bytes,
    *,
    expected_federation_sha256: str,
    local_domain: str,
    now_s: int,
    minimum_time_s: int,
    minimum_federation_revision: int,
) -> FederationValidation:
    """Validate even a deny-all table independently of any bundle.

    Pins, domain and time/floors come from trusted configuration. No I/O,
    signature verification, peer policy validation or persistence is performed.
    A result is a snapshot, not an authorization token; revalidate at use.
    """
    try:
        _token(expected_federation_sha256, _HEX)
        _token(local_domain)
        _integer(minimum_federation_revision, 1)
        _integer(now_s)
        _integer(minimum_time_s)
        snapshot, _ = _snapshot(_parse(federation))
        _require(_canonical(snapshot) == federation)
        digest = sha256(federation).hexdigest()
        if digest != expected_federation_sha256:
            return FederationValidation("rejected", "federation_mismatch")
        if snapshot["local_domain"] != local_domain:
            return FederationValidation("rejected", "local_domain_mismatch")
        if now_s < minimum_time_s or snapshot["revision"] < minimum_federation_revision:
            return FederationValidation("rejected", "federation_rollback")
        if not snapshot["issued_at"] <= now_s < snapshot["expires_at"]:
            return FederationValidation("rejected", "federation_not_current")
        return FederationValidation(
            "validated", "federation_matches", digest, snapshot["revision"], snapshot["expires_at"]
        )
    except (ValueError, TypeError, KeyError, RecursionError):
        return FederationValidation("rejected", "invalid_federation")


@dataclass(frozen=True)
class FederationVerification:
    status: str
    reason: str
    task_sha256: Optional[str] = None
    passport_sha256: Optional[str] = None
    federation_sha256: Optional[str] = None
    federation_revision: Optional[int] = None
    policy_revision: Optional[int] = None
    expires_at: Optional[int] = None
    evidence: Tuple[EvidenceReference, ...] = ()
    execution_authority: bool = field(default=False, init=False)
    motion_authority: bool = field(default=False, init=False)
    evidence_verified: bool = field(default=False, init=False)


def verify_federated_bundle(
    federation: bytes,
    task: bytes,
    envelope: bytes,
    policy: bytes,
    evidence: Tuple[bytes, ...],
    *,
    expected_federation_sha256: str,
    local_domain: str,
    remote_domain: str,
    minimum_federation_revision: int,
    expected_task_sha256: str,
    expected_subject_sha256: str,
    now_s: int,
    minimum_time_s: int,
    minimum_policy_revision: int,
) -> FederationVerification:
    """Revalidate a bundle under one externally pinned direct-peer snapshot."""
    try:
        _token(expected_federation_sha256, _HEX)
        _token(local_domain)
        _token(remote_domain)
        _integer(minimum_federation_revision, 1)
        _integer(now_s)
        _integer(minimum_time_s)
        snapshot, peers = _snapshot(_parse(federation))
        _require(_canonical(snapshot) == federation)
        digest = sha256(federation).hexdigest()
        if digest != expected_federation_sha256:
            return FederationVerification("rejected", "federation_mismatch")
        if snapshot["local_domain"] != local_domain:
            return FederationVerification("rejected", "local_domain_mismatch")
        if now_s < minimum_time_s or snapshot["revision"] < minimum_federation_revision:
            return FederationVerification("rejected", "federation_rollback")
        if not snapshot["issued_at"] <= now_s < snapshot["expires_at"]:
            return FederationVerification("rejected", "federation_not_current")
        if remote_domain not in peers:
            return FederationVerification("rejected", "untrusted_peer")
        peer = peers[remote_domain]
        _require(type(policy) is bytes and len(policy) <= 65536)
        if sha256(policy).hexdigest() != peer["policy_sha256"]:
            return FederationVerification("rejected", "peer_policy_mismatch")
        bound = verify_task_bundle(
            task,
            envelope,
            policy,
            evidence,
            expected_task_sha256=expected_task_sha256,
            expected_subject_sha256=expected_subject_sha256,
            now_s=now_s,
            minimum_time_s=minimum_time_s,
            minimum_policy_revision=minimum_policy_revision,
        )
        if bound.status != "bound":
            return FederationVerification("rejected", "bundle_rejected")
        # Bundle verification authenticated these exact immutable canonical bytes.
        statement = json.loads(
            base64.b64decode(json.loads(envelope.decode("utf-8"))["payload"], validate=True)
        )
        if statement["issuer"] not in peer["issuers"] or any(
            capability["name"] not in peer["capabilities"]
            for capability in statement["capabilities"]
        ):
            return FederationVerification("rejected", "peer_scope_mismatch")
        return FederationVerification(
            "bound",
            "direct_peer_scope_verified",
            bound.task_sha256,
            bound.passport_sha256,
            digest,
            snapshot["revision"],
            bound.policy_revision,
            min(snapshot["expires_at"], bound.expires_at),
            bound.evidence,
        )
    except (ValueError, TypeError, KeyError, RecursionError):
        return FederationVerification("rejected", "invalid_federation")
