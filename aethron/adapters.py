"""Reference adapters for minimized patches/cues; not device drivers.

Never supply camera images, person geometry, radar samples or object identities.
The caller owns sensor calibration, truthful quality and non-human exclusion.
"""

import json

from .schema import parse, require


def envelope(
    observations,
    *,
    now_ms,
    lighting="daylight",
    evidence="external_unverified",
    contract="warn",
    authorized_obstruction=False,
    zones=None,
    version=1,
    mode="direct",
):
    require(type(observations) is list and len(observations) <= 28)
    doc = {
        "version": version,
        "now_ms": now_ms,
        "clock": "monotonic",
        "lighting": lighting,
        "evidence": evidence,
        "authorized_obstruction": authorized_obstruction,
        "contract": contract,
        "zones": zones if zones is not None else ["near"],
        "observations": observations,
    }
    if version == 2:
        doc["mode"] = mode
    # Full closed-schema validation precedes returning any adapter output.
    from .schema import validate

    validate(doc)
    data = json.dumps(doc, allow_nan=False).encode()
    parse(data)
    return data


def _patch(
    sensor, values, at_ms, calibration_until_ms, zone, quality, nonhuman, rect, inference_ms
):
    obs = {
        "sensor": sensor,
        "zone": zone,
        "values": values,
        "at_ms": at_ms,
        "calibration_until_ms": calibration_until_ms,
        "quality": quality,
        "nonhuman": nonhuman,
        "rect": rect,
        "inference_ms": inference_ms,
    }
    envelope([obs], now_ms=at_ms, zones=[zone], authorized_obstruction=sensor == "radar")
    return obs


def thermal_patch(
    values,
    *,
    at_ms,
    calibration_until_ms,
    zone="near",
    quality="valid",
    nonhuman=False,
    rect=None,
    inference_ms=0,
):
    return _patch(
        "thermal", values, at_ms, calibration_until_ms, zone, quality, nonhuman, rect, inference_ms
    )


def depth_patch(
    values,
    *,
    at_ms,
    calibration_until_ms,
    zone="near",
    quality="valid",
    nonhuman=False,
    rect=None,
    inference_ms=0,
):
    return _patch(
        "depth_active",
        values,
        at_ms,
        calibration_until_ms,
        zone,
        quality,
        nonhuman,
        rect,
        inference_ms,
    )


def coarse_cue(
    sensor, score, *, zone, at_ms, calibration_until_ms, quality="valid", inference_ms=0
):
    require(sensor in ("rgb", "radar"))
    return _patch(
        sensor, [score], at_ms, calibration_until_ms, zone, quality, False, None, inference_ms
    )


def person_cue(
    sensor, score, *, at_ms, calibration_until_ms, rect=None, quality="valid", inference_ms=0
):
    """Current direct-view minimized human envelope. Upstream validation is external."""
    require(sensor in ("rgb", "thermal_person", "depth_person"))
    obs = {
        "sensor": sensor,
        "zone": "near",
        "values": [score],
        "at_ms": at_ms,
        "calibration_until_ms": calibration_until_ms,
        "quality": quality,
        "nonhuman": False,
        "rect": rect,
        "inference_ms": inference_ms,
    }
    envelope([obs], now_ms=at_ms, version=2)
    return obs
