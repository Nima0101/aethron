"""Match bounded supplied bytes to declarations; never authenticate instruments."""

import hashlib
import json
import re

from .evidence import validate

MAX_ARTIFACTS = 15
MAX_ARTIFACT_BYTES = 1048576
MAX_TOTAL_BYTES = 4194304


def _require(condition):
    if not condition:
        raise ValueError("invalid_qualification_artifacts")


def verify(manifest, artifacts, *, now_ms):
    """Report byte equality separately from declaration and physical validity."""
    try:
        declaration = validate(manifest, now_ms=now_ms)
        _require(type(artifacts) is dict and len(artifacts) <= MAX_ARTIFACTS)
        supplied = artifacts.copy()
        _require(len(supplied) <= MAX_ARTIFACTS)
        total = 0
        for digest, payload in supplied.items():
            _require(type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest) is not None)
            _require(type(payload) is bytes and len(payload) <= MAX_ARTIFACT_BYTES)
            total += len(payload)
            _require(total <= MAX_TOTAL_BYTES)
    except ValueError:
        raise ValueError("invalid_qualification_artifacts") from None

    # The same immutable bytes have already passed the strict v1 parser/schema.
    references = {row["artifact_sha256"] for row in json.loads(manifest)["records"]}
    missing = len(references - supplied.keys())
    unreferenced = len(supplied.keys() - references)
    mismatched = sum(
        hashlib.sha256(supplied[digest]).hexdigest() != digest
        for digest in references & supplied.keys()
    )
    findings = []
    for failed, code in (
        (mismatched, "artifact_digest_mismatch"),
        (missing, "artifact_missing"),
        (not references, "artifact_references_empty"),
        (unreferenced, "artifact_unreferenced"),
    ):
        if failed:
            findings.append(code)
    verified = not findings
    return {
        "version": 1,
        "declaration": declaration,
        "artifact_counts": {
            "referenced": len(references),
            "supplied": len(supplied),
            "matched": len(references) - missing - mismatched,
            "missing": missing,
            "mismatched": mismatched,
            "unreferenced": unreferenced,
            "supplied_bytes": total,
        },
        "artifact_findings": findings,
        "artifact_bytes_verified": verified,
        "software_checks_passed": verified and declaration["declaration_checks_passed"],
        "artifact_authenticity_verified": False,
        "physical_qualification_passed": False,
    }
