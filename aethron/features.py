"""Transparent rule features; no learned detection or identity inference."""

import hashlib
import json
from importlib import resources

# Frozen declarative artifact: reject even plausible substitutions.
MODEL_SHA256 = "0c1dad9a888f1f1e3513d0c2c983a7d240563b7945224efc0690f94dc676fee6"


def load_model(data=None):
    try:
        if data is None:
            with resources.files("aethron.models").joinpath("rules.json").open("rb") as stream:
                data = stream.read(2049)
        if (
            type(data) is bytes
            and len(data) <= 2048
            and hashlib.sha256(data).hexdigest() == MODEL_SHA256
        ):
            return json.loads(data)
        return None
    except (OSError, ModuleNotFoundError):
        return False


def capabilities(sensor):
    if sensor in ("rgb", "thermal_person", "depth_person"):
        return ("human_presence", "occupancy_zone")
    if sensor == "radar":
        return ("occupancy_zone",)
    return ("thermal_source",) if sensor.startswith("thermal") else ("obstacle",)


def extract(obs, request, model_ok):
    reasons = []
    now = request["now_ms"]
    if obs["quality"] != "valid":
        reasons.append(obs["quality"])
    if obs["at_ms"] > now:
        reasons.append("future")
    elif now - obs["at_ms"] > 500:
        reasons.append("stale")
    if obs["calibration_until_ms"] < max(now, obs["at_ms"]):
        reasons.append("calibration")
    if obs["inference_ms"] > 100:
        reasons.append("timeout")
    if obs["sensor"] in ("rgb", "depth_passive") and request["lighting"] != "daylight":
        reasons.append("darkness")
    if not obs["values"]:
        reasons.append("missing")
    if obs["sensor"] in ("depth_active", "depth_passive", "depth_aux") and 0 in obs["values"]:
        reasons.append("invalid_range")
    if not model_ok:
        reasons.append("model_error")
    if reasons:
        return None, reasons
    sensor, values = obs["sensor"], obs["values"]
    state, kind, score = "ABSENT", "none", 0.9
    if sensor in ("rgb", "radar", "thermal_person", "depth_person"):
        score = values[0]
        if model_ok["cue_absent_max"] < score < model_ok["cue_present_min"]:
            return None, ["uncertain"]
        if score >= model_ok["cue_present_min"]:
            state, kind = "PRESENT", "presence"
        else:
            score = 1 - score
    elif sensor.startswith("thermal"):
        if max(values) >= model_ok["thermal_fire_like_c"]:
            state, kind = "PRESENT", "fire_like"
        elif max(values) >= model_ok["thermal_hot_c"]:
            state, kind = "PRESENT", "hot"
        elif min(values) <= model_ok["thermal_cold_c"]:
            state, kind = "PRESENT", "cold"
    elif min(values) <= model_ok["obstacle_near_m"]:
        state, kind = "PRESENT", "obstacle"
    return {"state": state, "kind": kind, "score": score, "obs": obs}, []
