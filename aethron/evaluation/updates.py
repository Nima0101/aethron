"""Pinned offline registry update proposals; no persistent state or deployment authority."""

import hashlib

from .registry import validate as validate_entry
from .rights import _time
from .splits import _hash, _keys, _parse, _require

MAX_PROPOSAL_BYTES = 4096
MAX_REVISION = 2**53 - 1


def _revision(value):
    _require(type(value) is int and 0 <= value <= MAX_REVISION)


def validate(
    proposal,
    entry,
    *,
    candidate,
    card,
    rights,
    training_manifest,
    evaluation_manifest,
    evaluation_evidence,
    expected_proposal_sha256,
    expected_current_entry_sha256,
    current_revision,
    minimum_revision,
    expected_review_sha256,
    now_s,
    minimum_time_s,
    revoked_rights_sha256s,
):
    """Check a proposed successor against trusted current state and a revision floor.

    All entry gates run on supplied bytes, never on a caller-provided report.
    This pure check neither persists a revision nor makes concurrent checks atomic.
    """
    try:
        _require(type(proposal) is bytes and len(proposal) <= MAX_PROPOSAL_BYTES)
        _hash(expected_proposal_sha256)
        _require(hashlib.sha256(proposal).hexdigest() == expected_proposal_sha256)
        _hash(expected_current_entry_sha256)
        _revision(current_revision)
        _revision(minimum_revision)
        _require(current_revision >= minimum_revision)
        doc = _parse(proposal)
        _keys(
            doc,
            "version kind previous_entry_sha256 entry_sha256 revision valid_from_s expires_at_s",
        )
        _require(type(doc["version"]) is int and doc["version"] == 1)
        _require(doc["kind"] == "offline_registry_update")
        _require(doc["previous_entry_sha256"] == expected_current_entry_sha256)
        _hash(doc["entry_sha256"])
        _require(doc["entry_sha256"] != expected_current_entry_sha256)
        _revision(doc["revision"])
        _require(doc["revision"] == current_revision + 1)
        _time(doc["valid_from_s"])
        _time(doc["expires_at_s"])
        _require(doc["valid_from_s"] < doc["expires_at_s"])
        registry = validate_entry(
            entry,
            candidate=candidate,
            card=card,
            rights=rights,
            training_manifest=training_manifest,
            evaluation_manifest=evaluation_manifest,
            evaluation_evidence=evaluation_evidence,
            expected_entry_sha256=doc["entry_sha256"],
            expected_review_sha256=expected_review_sha256,
            now_s=now_s,
            minimum_time_s=minimum_time_s,
            revoked_rights_sha256s=revoked_rights_sha256s,
        )
        if now_s < doc["valid_from_s"]:
            reason = "not_yet_valid"
        elif now_s >= doc["expires_at_s"]:
            reason = "expired"
        else:
            reason = "declared_window_active"
        return {
            "version": 1,
            "check": "offline_registry_update_v1",
            "proposal_sha256": expected_proposal_sha256,
            "previous_entry_sha256": expected_current_entry_sha256,
            "current_revision": current_revision,
            "minimum_revision": minimum_revision,
            "revision": doc["revision"],
            "valid_from_s": doc["valid_from_s"],
            "expires_at_s": doc["expires_at_s"],
            "proposal_structure_valid": True,
            "proposal_reason": reason,
            "declaration_checks_passed": (
                reason == "declared_window_active" and registry["rights_declaration_active"]
            ),
            "registry": registry,
            "state_committed": False,
            "signatures_verified": False,
            "qualified": False,
            "runtime_admitted": False,
        }
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise ValueError("invalid_registry_update") from None
