"""Stateless, deterministic fusion of bounded, minimized observations."""

from .actions import recommend
from .features import capabilities, extract, load_model
from .schema import CAPABILITIES, parse, require


def fuse(capability, zone, observations, request, model_ok):
    valid, reasons = [], []
    for obs in observations:
        feature, invalid = extract(obs, request, model_ok)
        reasons.extend(invalid)
        if feature is not None:
            valid.append(feature)
    result = {
        "capability": capability,
        "zone": zone,
        "state": "UNKNOWN",
        "kind": "none",
        "confidence": "unavailable",
        "confidence_semantics": "uncalibrated_score",
        "reasons": [],
        "sources": [],
        "rect": None,
        "valid_until_ms": request["now_ms"] + 200,
    }
    if not valid:
        reasons.append("missing_valid_evidence")
    else:
        signatures = {(f["state"], f["kind"]) for f in valid}
        times = [f["obs"]["at_ms"] for f in valid]
        if len(signatures) != 1:
            reasons.append("disagreement")
        if max(times) - min(times) > 100:
            reasons.append("skew")
        if "disagreement" not in reasons and "skew" not in reasons:
            state, kind = next(iter(signatures))
            result["state"] = state
            result["kind"] = (
                "human" if capability == "human_presence" and state == "PRESENT" else kind
            )
            result["confidence"] = "high" if min(f["score"] for f in valid) >= 0.9 else "medium"
            result["valid_until_ms"] = min(
                [request["now_ms"] + 200]
                + [min(f["obs"]["at_ms"] + 500, f["obs"]["calibration_until_ms"]) for f in valid]
            )
            rects = [f["obs"]["rect"] for f in valid]
            if (
                state == "PRESENT"
                and capability in ("thermal_source", "obstacle")
                and all(f["obs"]["nonhuman"] for f in valid)
                and all(r == rects[0] for r in rects)
            ):
                result["rect"] = rects[0]
    if result["state"] != "UNKNOWN":
        result["sources"] = sorted(f["obs"]["sensor"] for f in valid)
    if request["version"] == 2:
        if result["state"] == "PRESENT" and capability == "human_presence":
            rects = [f["obs"]["rect"] for f in valid]
            if rects and rects[0] is not None and all(r == rects[0] for r in rects):
                result["rect"] = rects[0]
            else:
                reasons.append("localization_uncertain")
    if reasons and result["confidence"] == "high":
        result["confidence"] = "medium"
    result["reasons"] = sorted(set(reasons))
    return result


def evaluate(data, *, model_bytes=None):
    """Evaluate protocol bytes. Caller supplies trusted monotonic time; no I/O except bundled model."""
    request = parse(data)
    require(request["version"] in (1, 2))
    model_ok = load_model(model_bytes)
    claims = []
    for zone in sorted(request["zones"]):
        for cap in CAPABILITIES:
            observations = [
                o
                for o in request["observations"]
                if o["zone"] == zone and cap in capabilities(o["sensor"])
            ]
            claims.append(fuse(cap, zone, observations, request, model_ok))
    result = {
        "version": request["version"],
        "evidence": request["evidence"],
        "lighting": request["lighting"],
        "degraded": any(c["state"] == "UNKNOWN" or c["reasons"] for c in claims),
        "claims": claims,
        "recommendation": recommend(request["contract"], claims),
        "valid_until_ms": min(c["valid_until_ms"] for c in claims),
    }

    if request["version"] == 2:
        result["mode"] = request["mode"]
    return result
