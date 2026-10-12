"""Bind opaque domain/procedure bytes to a plan without authenticating either."""

import hashlib

from .campaign import _inputs

MAX_REFERENCE_BYTES = 1048576


def bind(plan_bytes, domain_bytes, procedure_bytes):
    """Check exact immutable byte matches; never approve content or qualification."""
    try:
        plan, _ = _inputs(plan_bytes, [])
        for payload in (domain_bytes, procedure_bytes):
            if type(payload) is not bytes or len(payload) > MAX_REFERENCE_BYTES:
                raise ValueError("invalid_campaign_references")
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid_campaign_references") from None
    findings = [
        kind + "_digest_mismatch"
        for kind, payload in (("domain", domain_bytes), ("procedure", procedure_bytes))
        if hashlib.sha256(payload).hexdigest() != plan[kind + "_sha256"]
    ]
    return {
        "version": 1,
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "reference_counts": {
            "supplied": 2,
            "matched": 2 - len(findings),
            "supplied_bytes": len(domain_bytes) + len(procedure_bytes),
        },
        "reference_findings": findings,
        "reference_bytes_verified": not findings,
        "domain_verified": False,
        "procedure_verified": False,
        "artifact_authenticity_verified": False,
        "physical_qualification_passed": False,
    }
