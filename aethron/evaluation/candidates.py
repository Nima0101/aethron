"""Pinned offline candidate declarations and opaque byte checks; no model execution."""

import argparse
import hashlib
import json
import os
import sys

from .splits import MAX_TOTAL_BYTES, _hash, _keys, _parse, _read_document, _require, _verify_blob
from .splits import validate as validate_manifest
from .splits import verify_artifacts as verify_dataset_artifacts

MAX_CANDIDATE_BYTES = 16384
FIELDS = (
    "version task format artifact_sha256 preprocessing_sha256 protocol_sha256 "
    "training_manifest_sha256 training_split card_sha256 rights_sha256"
)
BLOB_FIELDS = ("artifact_sha256", "preprocessing_sha256", "card_sha256", "rights_sha256")


def validate(
    data, manifest, *, expected_candidate_sha256, expected_manifest_sha256, expected_protocol_sha256
):
    """Check declared bindings only; caller pins must come from trusted configuration."""
    try:
        _require(type(data) is bytes and len(data) <= MAX_CANDIDATE_BYTES)
        doc = _parse(data)
        _keys(doc, FIELDS)
        _require(type(doc["version"]) is int and doc["version"] == 1)
        _require(doc["task"] == "obstacle_proposals" and doc["format"] == "opaque")
        _require(doc["training_split"] == "train")
        for key in (*BLOB_FIELDS, "protocol_sha256", "training_manifest_sha256"):
            _hash(doc[key])
        for pin in (expected_candidate_sha256, expected_manifest_sha256, expected_protocol_sha256):
            _hash(pin)
        _require(hashlib.sha256(data).hexdigest() == expected_candidate_sha256)
        dataset = validate_manifest(manifest)
        _require(
            dataset["manifest_sha256"]
            == expected_manifest_sha256
            == doc["training_manifest_sha256"]
        )
        _require(dataset["protocol_sha256"] == expected_protocol_sha256 == doc["protocol_sha256"])
        return {
            "version": 1,
            "candidate_sha256": expected_candidate_sha256,
            **{key: doc[key] for key in FIELDS.split() if key != "version"},
            "training_samples": dataset["counts"]["train"],
            "artifacts_verified": False,
            "rights_verified": False,
            "signatures_verified": False,
            "training_verified": False,
            "preprocessing_verified": False,
            "qualified": False,
        }
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise ValueError("invalid_model_candidate") from None


def verify_artifacts(
    data,
    manifest,
    blob_dir,
    *,
    expected_candidate_sha256,
    expected_manifest_sha256,
    expected_protocol_sha256,
):
    """Hash all dataset references and candidate blobs, without parsing candidate payloads."""
    result = validate(
        data,
        manifest,
        expected_candidate_sha256=expected_candidate_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_protocol_sha256=expected_protocol_sha256,
    )
    try:
        dataset = verify_dataset_artifacts(manifest, blob_dir)
        total = dataset["verified_bytes"]
        digests = sorted({result[key] for key in BLOB_FIELDS})
        root_fd = os.open(os.path.normpath(blob_dir), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for digest in digests:
                size, _ = _verify_blob(root_fd, digest, MAX_TOTAL_BYTES - total)
                total += size
        finally:
            os.close(root_fd)
        return dict(
            result,
            artifacts_verified=True,
            verified_bytes=total,
            verified_blob_reads=dataset["verified_blobs"] + len(digests),
        )
    except (OSError, ValueError, TypeError, AttributeError, OverflowError, NotImplementedError):
        raise ValueError("invalid_model_candidate") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate")
    parser.add_argument("--training-manifest", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--blob-dir", help="Optionally verify local SHA-256-named blobs")
    args = parser.parse_args()
    try:
        data = _read_document(args.candidate)
        manifest = _read_document(args.training_manifest)
        pins = {
            "expected_candidate_sha256": args.candidate_sha256,
            "expected_manifest_sha256": args.manifest_sha256,
            "expected_protocol_sha256": args.protocol_sha256,
        }
        result = (
            verify_artifacts(data, manifest, args.blob_dir, **pins)
            if args.blob_dir is not None
            else validate(data, manifest, **pins)
        )
    except (OSError, ValueError, AttributeError, NotImplementedError):
        print("invalid_model_candidate", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
