"""Pinned candidate/test separation declarations; no artifact or rights qualification."""

import argparse
import json
import sys

from .candidates import validate as validate_candidate
from .splits import _hash, _parse, _read_document, _require
from .splits import validate as validate_manifest


def validate(
    candidate,
    training_manifest,
    evaluation_manifest,
    *,
    expected_candidate_sha256,
    expected_manifest_sha256,
    expected_evaluation_manifest_sha256,
    expected_protocol_sha256,
):
    """Reject declared test overlap with candidate training/validation content or sessions.

    Both manifests must independently pass split validation. Caller pins come from
    trusted configuration. No referenced files are read or model bytes executed.
    """
    try:
        _hash(expected_evaluation_manifest_sha256)
        model = validate_candidate(
            candidate,
            training_manifest,
            expected_candidate_sha256=expected_candidate_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_protocol_sha256=expected_protocol_sha256,
        )
        evaluation = validate_manifest(evaluation_manifest)
        _require(evaluation["manifest_sha256"] == expected_evaluation_manifest_sha256)
        _require(evaluation["protocol_sha256"] == expected_protocol_sha256)
        development = [
            row
            for row in _parse(training_manifest)["samples"]
            if row["split"] in ("train", "validation")
        ]
        content = {row[key] for row in development for key in ("source_sha256", "artifact_sha256")}
        sessions = {row["session_sha256"] for row in development}
        for row in _parse(evaluation_manifest)["samples"]:
            if row["split"] == "test":
                _require(row["source_sha256"] not in content)
                _require(row["artifact_sha256"] not in content)
                _require(row["session_sha256"] not in sessions)
        return {
            "version": 1,
            "check": "candidate_test_separation_v1",
            "candidate_sha256": model["candidate_sha256"],
            "training_manifest_sha256": model["training_manifest_sha256"],
            "evaluation_manifest_sha256": evaluation["manifest_sha256"],
            "protocol_sha256": model["protocol_sha256"],
            "development_samples": len(development),
            "evaluation_samples": evaluation["counts"]["test"],
            "declared_test_separation": True,
            "artifacts_verified": False,
            "rights_verified": False,
            "training_verified": False,
            "qualified": False,
        }
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise ValueError("invalid_candidate_holdout") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate")
    for name in (
        "training-manifest",
        "evaluation-manifest",
        "candidate-sha256",
        "manifest-sha256",
        "evaluation-manifest-sha256",
        "protocol-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    try:
        result = validate(
            _read_document(args.candidate),
            _read_document(args.training_manifest),
            _read_document(args.evaluation_manifest),
            expected_candidate_sha256=args.candidate_sha256,
            expected_manifest_sha256=args.manifest_sha256,
            expected_evaluation_manifest_sha256=args.evaluation_manifest_sha256,
            expected_protocol_sha256=args.protocol_sha256,
        )
    except (OSError, ValueError, AttributeError, NotImplementedError):
        print("invalid_candidate_holdout", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
