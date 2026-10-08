"""Same-frame registered geometry fusion without assuming sensor independence."""

from .math import iou


def observations(frame, now):
    detections, reasons = [], []
    eligible = []
    for s in frame["sensors"]:
        kind = s["kind"]
        reason = None
        if s["quality"] != "valid":
            reason = s["quality"]
        elif not s["registered"]:
            reason = "unregistered"
        elif not 0 <= now - s["at_ms"] <= 100 or s["at_ms"] > frame["at_ms"]:
            reason = "timestamp"
        elif s["calibration_until_ms"] < now:
            reason = "calibration"
        elif kind == "rgb" and frame["lighting"] != "daylight":
            reason = "darkness"
        if reason:
            reasons.append(kind + ":" + reason)
        else:
            eligible.append(s)
    if eligible and max(s["at_ms"] for s in eligible) - min(s["at_ms"] for s in eligible) > 50:
        return [], sorted(reasons + ["sensor_skew"])
    for s in eligible:
        for d in s["detections"]:
            if d["score"] < 0.35:
                continue
            detections.append(
                dict(
                    d,
                    sources=[s["kind"]],
                    at_ms=s["at_ms"],
                    until_ms=min(s["at_ms"] + 100, s["calibration_until_ms"]),
                )
            )
    detections.sort(key=lambda d: (d["class"], tuple(d["box"]), d["sources"][0], d["score"]))
    # Only unambiguous cross-sensor overlap; no transitive many-to-one joining.
    used, result = set(), []
    for i, d in enumerate(detections):
        if i in used:
            continue
        group = [d]
        used.add(i)
        for j, e in enumerate(detections):
            if j in used or d["class"] != e["class"]:
                continue
            if any(e["sources"] == f["sources"] for f in group):
                continue
            if iou(d["box"], e["box"]) < 0.5:
                continue
            competing = [
                k
                for k, f in enumerate(detections)
                if k != j
                and f["sources"] == d["sources"]
                and f["class"] == e["class"]
                and iou(e["box"], f["box"]) >= 0.5
            ]
            reverse = [
                k
                for k, f in enumerate(detections)
                if k != i
                and f["sources"] == e["sources"]
                and f["class"] == d["class"]
                and iou(d["box"], f["box"]) >= 0.5
            ]
            if competing != [i] or reverse != [j]:
                reasons.append("fusion_ambiguous")
                continue
            group.append(e)
            used.add(j)
        # Preserve a measured rectangle from the most precise contributor.
        best = min(group, key=lambda f: (f["variance"], f["sources"][0]))
        ranges = [f["range_m"] for f in group if f["range_m"] is not None]
        disagreement = ranges and max(ranges) - min(ranges) > max(1.0, min(ranges) * 0.2)
        if disagreement:
            reasons.append("range_disagreement")
        result.append(
            dict(
                best,
                score=min(f["score"] for f in group),
                variance=max(f["variance"] for f in group),
                sources=sorted(f["sources"][0] for f in group),
                at_ms=min(f["at_ms"] for f in group),
                until_ms=min(f["until_ms"] for f in group),
                range_m=None if disagreement else (min(ranges) if ranges else None),
            )
        )
    return result, sorted(set(reasons))
