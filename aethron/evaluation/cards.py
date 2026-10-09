"""Bounded, pinned offline candidate-card declarations; no semantic or rights approval."""

import argparse
import hashlib
import json
import sys

from .candidates import validate as validate_candidate
from .splits import _keys, _parse, _read_document, _require, _text, _token

MAX_CARD_BYTES = 16384
BINDINGS = (
    "artifact_sha256",
    "preprocessing_sha256",
    "protocol_sha256",
    "training_manifest_sha256",
    "rights_sha256",
)
FORBIDDEN_USES = frozenset(
    (
        "biometric_identity",
        "cross_scene_reidentification",
        "person_history",
        "targeting",
        "weapons",
        "autonomous_pursuit",
        "live_safety",
    )
)
FIELDS = (
    "version task format format_version source origin license intended_use "
    "forbidden_uses reproducibility limitations " + " ".join(BINDINGS)
)


def _metadata(value):
    _text(value)
    _require(value.isprintable())


def validate(
    card,
    candidate,
    manifest,
    *,
    expected_candidate_sha256,
    expected_manifest_sha256,
    expected_protocol_sha256,
):
    """Bind card bytes through the trusted candidate pin; never execute card instructions."""
    try:
        _require(type(card) is bytes and len(card) <= MAX_CARD_BYTES)
        model = validate_candidate(
            candidate,
            manifest,
            expected_candidate_sha256=expected_candidate_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_protocol_sha256=expected_protocol_sha256,
        )
        _require(hashlib.sha256(card).hexdigest() == model["card_sha256"])
        doc = _parse(card)
        _keys(doc, FIELDS)
        _require(type(doc["version"]) is int and doc["version"] == 1)
        _require(doc["task"] == model["task"] and doc["format"] == model["format"])
        for key in BINDINGS:
            _require(doc[key] == model[key])
        _token(doc["format_version"])
        for key in ("source", "origin", "license", "reproducibility"):
            _metadata(doc[key])
        _require(doc["intended_use"] == "offline_obstacle_evaluation")
        uses = doc["forbidden_uses"]
        _require(type(uses) is list and len(uses) == len(FORBIDDEN_USES))
        _require(all(type(use) is str for use in uses) and set(uses) == FORBIDDEN_USES)
        limitations = doc["limitations"]
        _require(type(limitations) is list and 1 <= len(limitations) <= 16)
        for limitation in limitations:
            _metadata(limitation)
        _require(len(set(limitations)) == len(limitations))
        return {
            "version": 1,
            "check": "candidate_card_declarations_v1",
            **{key: model[key] for key in ("candidate_sha256", "card_sha256", *BINDINGS)},
            "card_structure_valid": True,
            "artifacts_verified": False,
            "rights_verified": False,
            "training_verified": False,
            "qualified": False,
        }
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise ValueError("invalid_candidate_card") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("card")
    for name in (
        "candidate",
        "training-manifest",
        "candidate-sha256",
        "manifest-sha256",
        "protocol-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    try:
        result = validate(
            _read_document(args.card),
            _read_document(args.candidate),
            _read_document(args.training_manifest),
            expected_candidate_sha256=args.candidate_sha256,
            expected_manifest_sha256=args.manifest_sha256,
            expected_protocol_sha256=args.protocol_sha256,
        )
    except (OSError, ValueError, AttributeError, NotImplementedError):
        print("invalid_candidate_card", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
