"""Recommendation-only integration contracts. Never connects to actuators."""

from .schema import CONTRACTS


def recommend(contract, claims):
    requires_fallback = any(c["state"] != "ABSENT" for c in claims)
    return {
        "contract": contract,
        "action": CONTRACTS[contract] if requires_fallback else "WARN",
        "reason": "hazard_or_unknown" if requires_fallback else "observe",
        "requires_independent_controller": True,
    }
