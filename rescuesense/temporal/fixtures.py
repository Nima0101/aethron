"""Original synthetic, frozen-rule sequences. Not sensor recordings or learned detector evidence."""

import json

from .schema import CLASSES


def detection(x=0.1, *, kind="person", y=0.45, w=0.04, h=0.08, score=0.9, range_m=None):
    return {
        "class": kind,
        "box": [x, y, w, h],
        "score": score,
        "variance": 0.0001,
        "range_m": range_m,
    }


def sensor(at, ds, kind="lwir", quality="valid"):
    return {
        "kind": kind,
        "at_ms": at,
        "quality": quality,
        "calibration_until_ms": at + 1000,
        "registered": True,
        "detections": ds,
    }


def frame(at, ds, *, kind="lwir", lighting="daylight", dx=0.0, dy=0.0):
    return {
        "version": 3,
        "at_ms": at,
        "lighting": lighting,
        "evidence": "synthetic",
        "mode": "direct",
        "contract": "vehicle_stop",
        "scene_break": False,
        "sensors": [sensor(at, ds, kind)],
        "ego": {"dx": dx, "dy": dy, "variance": 0.0, "valid": True},
    }


def encode(f):
    return json.dumps(f, sort_keys=True, separators=(",", ":")).encode("ascii")


def sequences():
    result = {}
    for name in (
        "clean",
        "occlusion",
        "fast_uav",
        "camera_pan",
        "blackout",
        "crossing",
        "all_loss",
    ):
        entries = []
        for i in range(24):
            fast = name == "fast_uav"
            speed = 0.018 if fast else 0.012
            dx = -0.008 if name == "camera_pan" else 0.0
            d = detection(
                0.1 + (speed + dx) * i,
                kind="uav" if fast else "person",
                w=0.012 if fast else 0.04,
                h=0.016 if fast else 0.08,
            )
            truth = [dict(d, id="truth-a")]
            ds = [d]
            if name == "crossing":
                other = detection(0.65 - 0.012 * i)
                ds.append(other)
                truth.append(dict(other, id="truth-b"))
            if name in ("occlusion", "fast_uav") and i in (8, 9, 16):
                ds = []
            if name == "all_loss" and i >= 8:
                ds = []
            f = frame(i * 100, ds, dx=dx if i else 0.0)
            if name == "blackout":
                f["lighting"] = "daylight" if i < 8 else "zero_visible"
                f["sensors"].append(sensor(i * 100, [dict(d)], "rgb", "valid" if i < 8 else "dark"))
                f["sensors"].append(sensor(i * 100, [dict(d, range_m=8.0)], "depth"))
                f["sensors"].append(sensor(i * 100, [dict(d, range_m=8.1)], "radar"))
            entries.append({"frame": f, "truth": truth})
        result[name] = entries
    result["classes"] = [
        {"frame": frame(i * 100, [detection(kind=c)]), "truth": [dict(detection(kind=c), id=c)]}
        for i, c in enumerate(CLASSES)
    ]
    return result
