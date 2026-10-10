"""Bounded capture declaration coverage; no device or domain qualification."""

import hashlib
import json
from collections import Counter

from aethron._json_bounds import check

from .evidence import (
    EVIDENCE,
    MAX_BYTES,
    _enum,
    _hash,
    _integer,
    _keys,
    _pairs,
    _parse_integer,
    _token,
    validate,
)

SENSORS = ("rgb", "lwir", "radar", "depth", "nir")
LIGHTING = ("daylight", "low_light", "near_dark", "zero_visible")
MAX_CAPTURES = 64


def _require(condition):
    if not condition:
        raise ValueError("invalid_capture_campaign")


def _inputs(plan_bytes, captures):
    _require(check(plan_bytes))
    plan = json.loads(
        plan_bytes.decode("utf-8"),
        object_pairs_hook=_pairs,
        parse_int=_parse_integer,
        parse_constant=lambda _: _require(False),
    )
    _keys(plan, "version rig_sha256 domain_sha256 procedure_sha256 cases")
    _require(type(plan["version"]) is int and plan["version"] == 1)
    for key in ("rig_sha256", "domain_sha256", "procedure_sha256"):
        _hash(plan[key])
    _require(type(plan["cases"]) is list and 1 <= len(plan["cases"]) <= 16)
    seen, total = set(), 0
    for case in plan["cases"]:
        _keys(case, "id lighting required_sensors evidence minimum_captures")
        _token(case["id"])
        _require(case["id"] not in seen)
        seen.add(case["id"])
        _enum(case["lighting"], LIGHTING)
        _enum(case["evidence"], EVIDENCE)
        _integer(case["minimum_captures"])
        _require(1 <= case["minimum_captures"] <= MAX_CAPTURES)
        total += case["minimum_captures"]
        sensors = case["required_sensors"]
        _require(type(sensors) is list and 1 <= len(sensors) <= 5)
        for sensor in sensors:
            _enum(sensor, SENSORS)
        _require(len(set(sensors)) == len(sensors))
    _require(total <= MAX_CAPTURES)
    _require(type(captures) is list and len(captures) <= MAX_CAPTURES)
    rows = []
    for capture in captures:
        _keys(capture, "case_id manifest now_ms")
        _token(capture["case_id"])
        _integer(capture["now_ms"])
        raw = capture["manifest"]
        _require(type(raw) is bytes and len(raw) <= MAX_BYTES)
        rows.append((capture["case_id"], raw, capture["now_ms"]))
    return plan, rows


def _capture_findings(raw, now_ms, case, rig_digest):
    try:
        report = validate(raw, now_ms=now_ms)
    except ValueError:
        return {"capture_invalid"}
    findings = {"declaration_" + code for code in report["findings"]}
    doc = json.loads(raw)  # Identical immutable bytes passed the strict schema.
    actual_rig = hashlib.sha256(
        json.dumps(doc["rig"], sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    if actual_rig != rig_digest:
        findings.add("capture_rig_mismatch")
    sensors = {row["kind"]: row["id"] for row in doc["rig"]["sensors"]}
    required = set(case["required_sensors"])
    if required - sensors.keys():
        findings.add("capture_sensor_missing")
    lighting = {
        row["sensor_id"]: row["data"]["lighting"]
        for row in doc["records"]
        if row["kind"] == "environment"
    }
    for kind in required & sensors.keys():
        if lighting.get(sensors[kind]) != case["lighting"]:
            findings.add("capture_lighting_mismatch")
    if any(row["evidence"] != case["evidence"] for row in doc["records"]):
        findings.add("capture_evidence_mismatch")
    return findings


def evaluate(plan_bytes, captures):
    """Evaluate all submitted attempts without treating declarations as truth."""
    try:
        plan, rows = _inputs(plan_bytes, captures)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid_capture_campaign") from None
    cases = {case["id"]: case for case in plan["cases"]}
    eligible = dict.fromkeys(cases, 0)
    # Count first: duplicates cannot win based on submission order or case name.
    digests = [hashlib.sha256(raw).digest() for _, raw, _ in rows]
    repeated = Counter(digests)
    findings = set()
    for (case_id, raw, now_ms), digest in zip(rows, digests):
        local = set()
        if repeated[digest] > 1:
            local.add("capture_reused")
        if case_id not in cases:
            local.add("capture_unplanned")
        else:
            local.update(_capture_findings(raw, now_ms, cases[case_id], plan["rig_sha256"]))
        if not local:
            eligible[case_id] += 1
        findings.update(local)
    results = [
        {
            "case_index": index,
            "required": case["minimum_captures"],
            "eligible": eligible[case["id"]],
        }
        for index, case in enumerate(plan["cases"])
    ]
    if any(row["eligible"] < row["required"] for row in results):
        findings.add("capture_coverage_missing")
    count = sum(eligible.values())
    bindings = sorted(
        (case_id, digest.hex(), now_ms) for (case_id, _, now_ms), digest in zip(rows, digests)
    )
    capture_digest = hashlib.sha256(
        b"aethron.qualification.captures.v1\0"
        + json.dumps(bindings, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return {
        "version": 1,
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "captures_sha256": capture_digest,
        "capture_counts": {
            "submitted": len(rows),
            "eligible": count,
            "rejected": len(rows) - count,
        },
        "cases": results,
        "findings": sorted(findings),
        "declaration_coverage_complete": not findings,
        "domain_verified": False,
        "procedure_verified": False,
        "artifact_authenticity_verified": False,
        "physical_qualification_passed": False,
    }
