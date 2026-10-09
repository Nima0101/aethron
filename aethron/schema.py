"""Closed, resource-bounded protocol. Errors never echo input content."""

import json
import math

from ._json_bounds import check as check_bounds

MAX_BYTES = 65536
MAX_TIME = 2**53 - 1000
ZONES = ("near", "sector_a", "sector_b", "sector_c")
SENSORS = ("rgb", "thermal", "thermal_aux", "depth_active", "depth_passive", "depth_aux", "radar")
CONTRACTS = {
    "warn": "WARN",
    "vehicle_stop": "STOP",
    "drone_hover": "HOVER",
    "drone_land": "LAND",
    "drone_retreat": "RETREAT",
}
CAPABILITIES = ("human_presence", "occupancy_zone", "thermal_source", "obstacle")


def require(condition):
    if not condition:
        raise ValueError("invalid_input")


def integer(value, low=0, high=MAX_TIME):
    require(type(value) is int and low <= value <= high)


def enum(value, options):
    require(type(value) is str and value in options)


def keys(obj, names):
    require(type(obj) is dict and set(obj) == set(names.split()))


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def parse(data):
    require(type(data) is bytes and len(data) <= MAX_BYTES)
    try:
        require(check_bounds(data))
        obj = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _: require(False),
        )
        validate(obj)
        return obj
    except (UnicodeError, ValueError, TypeError, OverflowError, RecursionError):
        raise ValueError("invalid_input") from None


def validate(obj):
    if type(obj) is dict and obj.get("version") == 3:
        from .temporal.schema import validate as validate_v3

        validate_v3(obj)
    elif type(obj) is dict and obj.get("version") == 2:
        from .schema_v2 import validate_v2

        validate_v2(obj)
    else:
        validate_v1(obj)


def validate_v1(obj):
    keys(
        obj,
        "version now_ms clock lighting evidence authorized_obstruction contract zones observations",
    )
    integer(obj["version"], 1, 1)
    integer(obj["now_ms"])
    enum(obj["clock"], ("monotonic",))
    enum(obj["lighting"], ("daylight", "low_light", "near_dark", "zero_visible"))
    enum(obj["evidence"], ("synthetic", "external_unverified"))
    enum(obj["contract"], CONTRACTS)
    require(type(obj["authorized_obstruction"]) is bool)
    zones = obj["zones"]
    require(type(zones) is list and 1 <= len(zones) <= 4)
    for zone in zones:
        enum(zone, ZONES)
    require(len(set(zones)) == len(zones))
    observations = obj["observations"]
    require(type(observations) is list and len(observations) <= 28)
    seen = set()
    for obs in observations:
        keys(
            obs, "sensor zone at_ms calibration_until_ms quality values inference_ms nonhuman rect"
        )
        sensor = obs["sensor"]
        enum(sensor, SENSORS)
        enum(obs["zone"], zones)
        pair = (sensor, obs["zone"])
        require(pair not in seen)
        seen.add(pair)
        integer(obs["at_ms"])
        integer(obs["calibration_until_ms"])
        integer(obs["inference_ms"], 0, 100000)
        enum(
            obs["quality"],
            (
                "valid",
                "dark",
                "saturated",
                "occluded",
                "noisy",
                "multipath",
                "dropped",
                "model_error",
            ),
        )
        require(type(obs["nonhuman"]) is bool)
        values = obs["values"]
        require(type(values) is list and len(values) <= 256)
        low, high = (-100, 1000) if sensor.startswith("thermal") else (0, 100)
        if sensor in ("rgb", "radar"):
            require(len(values) == 1 and not obs["nonhuman"])
            low, high = 0, 1
        for value in values:
            require(type(value) in (int, float))
            require(low <= value <= high and math.isfinite(value))
        if sensor == "rgb":
            require(obs["zone"] == "near")
        if sensor == "radar":
            require(obs["zone"] != "near" and obj["authorized_obstruction"])
        rect = obs["rect"]
        if rect is not None:
            require(sensor not in ("rgb", "radar") and obs["nonhuman"] and obs["zone"] == "near")
            require(type(rect) is list and len(rect) == 4)
            for value in rect:
                integer(value, 0, 100)
            x, y, width, height = rect
            require(width > 0 and height > 0 and x + width <= 100 and y + height <= 100)
