"""Versioned direct human-envelope extension; never through-obstruction geometry."""

from .schema import enum, keys, require, validate_v1

PERSON_SENSORS = ("rgb", "thermal_person", "depth_person")


def validate_v2(obj):
    keys(
        obj,
        "version mode now_ms clock lighting evidence authorized_obstruction contract zones observations",
    )
    enum(obj["mode"], ("direct", "through_obstruction"))
    require(type(obj["version"]) is int and obj["version"] == 2)
    observations = obj["observations"]
    require(type(observations) is list and len(observations) <= 28)
    base = dict(obj, version=1, observations=[])
    del base["mode"]
    validate_v1(base)
    if obj["mode"] == "through_obstruction":
        require(obj["authorized_obstruction"])
    seen = set()
    for obs in observations:
        keys(
            obs, "sensor zone at_ms calibration_until_ms quality values inference_ms nonhuman rect"
        )
        sensor = obs["sensor"]
        enum(
            sensor,
            (
                "rgb",
                "thermal_person",
                "depth_person",
                "thermal",
                "thermal_aux",
                "depth_active",
                "depth_passive",
                "depth_aux",
                "radar",
            ),
        )
        enum(obs["zone"], obj["zones"])
        pair = (sensor, obs["zone"])
        require(pair not in seen)
        seen.add(pair)
        require((obj["mode"] == "through_obstruction") == (sensor == "radar"))
        candidate = dict(obs)
        if sensor in PERSON_SENSORS:
            require(obs["zone"] == "near" and obs["nonhuman"] is False)
            values = obs["values"]
            require(type(values) is list and len(values) == 1)
            require(type(values[0]) in (int, float) and 0 <= values[0] <= 1)
            # Reuse rectangle/range structural checks without introducing an ID surface.
            candidate.update(sensor="thermal", nonhuman=True)
        validate_v1(dict(base, observations=[candidate]))
