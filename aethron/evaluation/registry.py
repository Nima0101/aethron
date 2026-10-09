"""Immutable offline registry-entry declarations; no model admission or qualification."""

import hashlib

from .cards import validate as validate_card
from .holdout import validate as validate_holdout
from .rights import assess as assess_rights
from .splits import _hash, _keys, _parse, _require

MAX_ENTRY_BYTES = 16384
DOCUMENT_LIMITS = (
    ("candidate", 16384),
    ("card", 16384),
    ("rights", 16384),
    ("training_manifest", 2 * 1024 * 1024),
    ("evaluation_manifest", 2 * 1024 * 1024),
    ("evaluation_evidence", 2 * 1024 * 1024),
)


def validate(
    entry,
    *,
    candidate,
    card,
    rights,
    training_manifest,
    evaluation_manifest,
    evaluation_evidence,
    expected_entry_sha256,
    expected_review_sha256,
    now_s,
    minimum_time_s,
    revoked_rights_sha256s,
):
    """Bind six documents and rerun declaration gates, preserving negative rights evidence.

    Caller configuration supplies trusted pins, time and revocations. Evaluation
    evidence is opaque: its byte identity establishes no metric or model claim.
    """
    try:
        _require(type(entry) is bytes and len(entry) <= MAX_ENTRY_BYTES)
        _hash(expected_entry_sha256)
        _require(hashlib.sha256(entry).hexdigest() == expected_entry_sha256)
        doc = _parse(entry)
        _keys(doc, "version kind protocol_sha256 documents")
        _require(type(doc["version"]) is int and doc["version"] == 1)
        _require(doc["kind"] == "offline_candidate")
        _hash(doc["protocol_sha256"])
        descriptors = doc["documents"]
        _keys(descriptors, " ".join(role for role, _ in DOCUMENT_LIMITS))
        documents = {
            "candidate": candidate,
            "card": card,
            "rights": rights,
            "training_manifest": training_manifest,
            "evaluation_manifest": evaluation_manifest,
            "evaluation_evidence": evaluation_evidence,
        }
        for role, limit in DOCUMENT_LIMITS:
            descriptor, raw = descriptors[role], documents[role]
            _keys(descriptor, "sha256 bytes")
            _hash(descriptor["sha256"])
            _require(type(descriptor["bytes"]) is int and 0 < descriptor["bytes"] <= limit)
            _require(type(raw) is bytes and len(raw) == descriptor["bytes"])
            _require(hashlib.sha256(raw).hexdigest() == descriptor["sha256"])
        pins = {
            "expected_candidate_sha256": descriptors["candidate"]["sha256"],
            "expected_manifest_sha256": descriptors["training_manifest"]["sha256"],
            "expected_protocol_sha256": doc["protocol_sha256"],
        }
        validate_card(card, candidate, training_manifest, **pins)
        validate_holdout(
            candidate,
            training_manifest,
            evaluation_manifest,
            expected_evaluation_manifest_sha256=descriptors["evaluation_manifest"]["sha256"],
            **pins,
        )
        rights_result = assess_rights(
            rights,
            candidate,
            training_manifest,
            expected_review_sha256=expected_review_sha256,
            operation="offline_evaluation",
            now_s=now_s,
            minimum_time_s=minimum_time_s,
            revoked_rights_sha256s=revoked_rights_sha256s,
            **pins,
        )
        return {
            "version": 1,
            "check": "candidate_registry_entry_v1",
            "entry_sha256": expected_entry_sha256,
            "protocol_sha256": doc["protocol_sha256"],
            "documents": descriptors,
            "registry_entry_valid": True,
            "card_structure_valid": True,
            "declared_test_separation": True,
            "rights_declaration_active": rights_result["declared_permission"],
            "rights_reason": rights_result["reason"],
            **{
                key: rights_result[key]
                for key in (
                    "review_sha256",
                    "evaluated_at_s",
                    "minimum_time_s",
                    "revocations_sha256",
                )
            },
            "evaluation_bytes_verified": True,
            "evaluation_semantics_verified": False,
            "model_artifacts_verified": False,
            "rights_verified": False,
            "review_verified": False,
            "dataset_rights_verified": False,
            "qualified": False,
            "runtime_admitted": False,
        }
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise ValueError("invalid_registry_entry") from None
