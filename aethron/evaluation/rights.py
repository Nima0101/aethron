"""Pinned, bounded candidate rights-review declarations; never legal authorization."""

import hashlib

from .candidates import validate as validate_candidate
from .splits import _hash, _keys, _parse, _require

MAX_RIGHTS_BYTES = 16384
MAX_REVOCATIONS = 1024
MAX_TIME_S = 2**53 - 1
USES = ("offline_evaluation", "offline_training", "artifact_redistribution")
BINDINGS = (
    "artifact_sha256",
    "preprocessing_sha256",
    "protocol_sha256",
    "training_manifest_sha256",
)
FIELDS = "version review_sha256 status uses valid_from_s expires_at_s " + " ".join(BINDINGS)


def _time(value):
    _require(type(value) is int and 0 <= value <= MAX_TIME_S)


def assess(
    rights,
    candidate,
    manifest,
    *,
    expected_candidate_sha256,
    expected_manifest_sha256,
    expected_protocol_sha256,
    expected_review_sha256,
    operation,
    now_s,
    minimum_time_s,
    revoked_rights_sha256s,
):
    """Evaluate declared scope using caller-controlled pins, time floor and revocations.

    The review evidence itself is not loaded or authenticated. A positive result
    reports only an active declaration, never permission to use an artifact.
    """
    try:
        _require(type(rights) is bytes and len(rights) <= MAX_RIGHTS_BYTES)
        _hash(expected_review_sha256)
        _time(now_s)
        _time(minimum_time_s)
        _require(now_s >= minimum_time_s)
        _require(type(operation) is str and operation in USES)
        _require(
            type(revoked_rights_sha256s) is tuple and len(revoked_rights_sha256s) <= MAX_REVOCATIONS
        )
        for digest in revoked_rights_sha256s:
            _hash(digest)
        revocations_sha256 = hashlib.sha256(
            b"aethron.rights-revocations.v1\0"
            + b"".join(digest.encode("ascii") for digest in sorted(set(revoked_rights_sha256s)))
        ).hexdigest()
        model = validate_candidate(
            candidate,
            manifest,
            expected_candidate_sha256=expected_candidate_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_protocol_sha256=expected_protocol_sha256,
        )
        _require(hashlib.sha256(rights).hexdigest() == model["rights_sha256"])
        doc = _parse(rights)
        _keys(doc, FIELDS)
        _require(type(doc["version"]) is int and doc["version"] == 1)
        for key in BINDINGS:
            _require(doc[key] == model[key])
        _require(doc["review_sha256"] == expected_review_sha256)
        status = doc["status"]
        _require(type(status) is str and status in ("approved", "denied", "pending", "revoked"))
        uses = doc["uses"]
        _require(type(uses) is list and len(uses) <= len(USES))
        _require(all(type(use) is str and use in USES for use in uses))
        _require(len(set(uses)) == len(uses) and (status != "approved" or bool(uses)))
        _time(doc["valid_from_s"])
        _time(doc["expires_at_s"])
        _require(doc["valid_from_s"] < doc["expires_at_s"])
        if model["rights_sha256"] in revoked_rights_sha256s:
            reason = "record_revoked"
        elif status != "approved":
            reason = "review_" + status
        elif now_s < doc["valid_from_s"]:
            reason = "not_yet_valid"
        elif now_s >= doc["expires_at_s"]:
            reason = "expired"
        elif operation not in uses:
            reason = "out_of_scope"
        else:
            reason = "declared_scope_active"
        return {
            "version": 1,
            "check": "candidate_rights_declarations_v1",
            **{key: model[key] for key in ("candidate_sha256", "rights_sha256", *BINDINGS)},
            "review_sha256": expected_review_sha256,
            "operation": operation,
            "evaluated_at_s": now_s,
            "minimum_time_s": minimum_time_s,
            "revocations_sha256": revocations_sha256,
            "declared_permission": reason == "declared_scope_active",
            "reason": reason,
            "rights_verified": False,
            "review_verified": False,
            "dataset_rights_verified": False,
            "qualified": False,
        }
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise ValueError("invalid_candidate_rights") from None
