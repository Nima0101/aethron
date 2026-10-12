"""Compose bounded campaign checks without accepting precomputed approvals."""

from .campaign import evaluate as evaluate_coverage
from .campaign_references import bind


def evaluate(plan_bytes, captures, domain_bytes, procedure_bytes):
    """Evaluate both gates against the same immutable plan; never qualify hardware."""
    try:
        references = bind(plan_bytes, domain_bytes, procedure_bytes)
        coverage = evaluate_coverage(plan_bytes, captures)
    except ValueError:
        raise ValueError("invalid_campaign_bundle") from None
    return {
        "version": 1,
        "plan_sha256": coverage["plan_sha256"],
        "coverage": coverage,
        "references": references,
        "software_checks_passed": (
            coverage["declaration_coverage_complete"] and references["reference_bytes_verified"]
        ),
        "artifact_bytes_verified": False,
        "artifact_authenticity_verified": False,
        "domain_verified": False,
        "procedure_verified": False,
        "physical_qualification_passed": False,
    }
