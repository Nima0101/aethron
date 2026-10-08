"""V3 has no caller IDs, embeddings, histories, hidden-person mode or action extensions."""

import math

from ..schema import CONTRACTS, enum, integer, keys, require

CLASSES = (
    "person",
    "cyclist",
    "vehicle",
    "uav",
    "animal",
    "obstacle",
    "equipment",
    "hot",
    "cold",
    "fire_like",
    "smoke",
)
KINDS = ("rgb", "lwir", "radar", "depth", "nir")


def number(value, low, high):
    require(type(value) in (int, float) and math.isfinite(value) and low <= value <= high)


def validate(obj):
    keys(obj, "version at_ms lighting evidence mode contract scene_break sensors ego")
    integer(obj["version"], 3, 3)
    integer(obj["at_ms"])
    enum(obj["lighting"], ("daylight", "low_light", "near_dark", "zero_visible"))
    enum(obj["evidence"], ("synthetic", "recorded", "external_unverified"))
    enum(obj["mode"], ("direct",))
    enum(obj["contract"], CONTRACTS)
    require(type(obj["scene_break"]) is bool)
    ego = obj["ego"]
    keys(ego, "dx dy variance valid")
    require(type(ego["valid"]) is bool)
    number(ego["dx"], -0.25, 0.25)
    number(ego["dy"], -0.25, 0.25)
    number(ego["variance"], 0, 0.05)
    sensors = obj["sensors"]
    require(type(sensors) is list and len(sensors) <= 5)
    seen, count = set(), 0
    for sensor in sensors:
        keys(sensor, "kind at_ms quality calibration_until_ms registered detections")
        enum(sensor["kind"], KINDS)
        require(sensor["kind"] not in seen)
        seen.add(sensor["kind"])
        integer(sensor["at_ms"])
        integer(sensor["calibration_until_ms"])
        enum(
            sensor["quality"],
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
        require(type(sensor["registered"]) is bool)
        require(type(sensor["detections"]) is list and len(sensor["detections"]) <= 64)
        count += len(sensor["detections"])
        require(count <= 64)
        for det in sensor["detections"]:
            keys(det, "class box score variance range_m")
            enum(det["class"], CLASSES)
            box = det["box"]
            require(type(box) is list and len(box) == 4)
            for v in box:
                number(v, 0, 1)
            require(box[2] > 0 and box[3] > 0 and box[0] + box[2] <= 1 and box[1] + box[3] <= 1)
            number(det["score"], 0, 1)
            number(det["variance"], 0.000001, 1)
            if det["range_m"] is not None:
                require(sensor["kind"] in ("depth", "radar"))
                number(det["range_m"], 0.000001, 500)
