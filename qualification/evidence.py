"""Bounded rig/evidence declaration validation with explicit unverified claims."""

import hashlib
import json
import re

from aethron._json_bounds import check

MAX_BYTES = 65536
MAX_TIME = 2**53 - 1000
EVIDENCE = ("synthetic", "recorded", "external_unverified")
KINDS = ("calibration", "clock", "environment")


def _require(condition):
    if not condition:
        raise ValueError("invalid_qualification_manifest")


def _keys(value, names):
    _require(type(value) is dict and set(value) == set(names.split()))


def _token(value):
    _require(type(value) is str and re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", value) is not None)


def _hash(value):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None)


def _integer(value, minimum=0):
    _require(type(value) is int and minimum <= value <= MAX_TIME)


def _enum(value, allowed):
    _require(type(value) is str and value in allowed)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _parse_integer(value):
    # Bound decimal conversion even on Python versions without an integer limit.
    _require(len(value) <= 17)
    return int(value)


def _schema(doc):
    _keys(doc, "version rig capture records")
    _require(type(doc["version"]) is int and doc["version"] == 1)
    rig = doc["rig"]
    _keys(rig, "id configuration_sha256 sensors")
    _token(rig["id"])
    _hash(rig["configuration_sha256"])
    sensors = rig["sensors"]
    _require(type(sensors) is list and 1 <= len(sensors) <= 5)
    ids, modalities = set(), set()
    for sensor in sensors:
        _keys(sensor, "id kind device_sha256 mount_sha256")
        _token(sensor["id"])
        _enum(sensor["kind"], ("rgb", "lwir", "radar", "depth", "nir"))
        _require(sensor["id"] not in ids and sensor["kind"] not in modalities)
        ids.add(sensor["id"])
        modalities.add(sensor["kind"])
        _hash(sensor["device_sha256"])
        _hash(sensor["mount_sha256"])
    capture = doc["capture"]
    _keys(capture, "clock_domain start_ms end_ms")
    _token(capture["clock_domain"])
    for key in ("start_ms", "end_ms"):
        _integer(capture[key])
    _require(capture["start_ms"] <= capture["end_ms"])
    records = doc["records"]
    _require(type(records) is list and len(records) <= 15)
    seen = set()
    for record in records:
        _keys(record, "sensor_id kind evidence artifact_sha256 rig_sha256 clock_domain data")
        _token(record["sensor_id"])
        _require(record["sensor_id"] in ids)
        _enum(record["kind"], KINDS)
        key = (record["sensor_id"], record["kind"])
        _require(key not in seen)
        seen.add(key)
        _enum(record["evidence"], EVIDENCE)
        _hash(record["artifact_sha256"])
        _hash(record["rig_sha256"])
        _token(record["clock_domain"])
        data = record["data"]
        if record["kind"] == "calibration":
            _keys(data, "valid_from_ms valid_until_ms")
            _integer(data["valid_from_ms"])
            _integer(data["valid_until_ms"])
            _require(data["valid_from_ms"] <= data["valid_until_ms"])
        elif record["kind"] == "clock":
            _keys(data, "at_ms offset_ms uncertainty_ms")
            _integer(data["at_ms"])
            _integer(data["offset_ms"], -MAX_TIME)
            _integer(data["uncertainty_ms"])
        else:
            _keys(data, "at_ms lighting")
            _integer(data["at_ms"])
            _enum(data["lighting"], ("daylight", "low_light", "near_dark", "zero_visible"))


def _findings(doc, now_ms):
    findings = set()
    capture = doc["capture"]
    start, end = capture["start_ms"], capture["end_ms"]
    if end > now_ms:
        findings.add("capture_future")
    elif now_ms - end > 100:
        findings.add("capture_stale")
    rig_digest = hashlib.sha256(
        json.dumps(doc["rig"], sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    seen, clocks = set(), []
    for record in doc["records"]:
        kind, data = record["kind"], record["data"]
        seen.add((record["sensor_id"], kind))
        if record["rig_sha256"] != rig_digest:
            findings.add("rig_binding_mismatch")
        same_domain = record["clock_domain"] == capture["clock_domain"]
        if not same_domain:
            findings.add("clock_domain_mismatch")
            continue  # Never compare milliseconds from different clock domains.
        if kind == "calibration":
            if data["valid_from_ms"] > start or data["valid_until_ms"] < end:
                findings.add("calibration_interval")
        else:
            if not start <= data["at_ms"] <= end:
                findings.add("record_outside_capture")
            if end - data["at_ms"] > 100:
                findings.add("record_stale")
            if kind == "clock":
                clocks.append(data)
                if abs(data["offset_ms"]) + data["uncertainty_ms"] > 50:
                    findings.add("clock_reference_skew")
    for index, left in enumerate(clocks):
        for right in clocks[index + 1 :]:
            skew = (
                abs(left["offset_ms"] - right["offset_ms"])
                + left["uncertainty_ms"]
                + right["uncertainty_ms"]
            )
            if skew > 50:
                findings.add("clock_pair_skew")
    for sensor in doc["rig"]["sensors"]:
        for kind in KINDS:
            if (sensor["id"], kind) not in seen:
                findings.add("missing_" + kind)
    return sorted(findings)


def validate(data, *, now_ms):
    """Validate exact bytes at a caller-supplied instant; never certify evidence."""
    try:
        _integer(now_ms)
        _require(check(data))
        doc = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_int=_parse_integer,
            parse_constant=lambda _: _require(False),
        )
        _schema(doc)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid_qualification_manifest") from None
    findings = _findings(doc, now_ms)
    counts = dict.fromkeys(EVIDENCE, 0)
    for record in doc["records"]:
        counts[record["evidence"]] += 1
    return {
        "version": 1,
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "declaration_checks_passed": not findings,
        "sensor_count": len(doc["rig"]["sensors"]),
        "record_count": len(doc["records"]),
        "evidence_counts": counts,
        "findings": findings,
        "artifacts_verified": False,
        "physical_qualification_passed": False,
        "physical_status": "blocked_external_evidence_and_review",
    }
