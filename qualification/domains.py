"""Bounded declaration coverage of joint domain profiles; no domain approval."""

import hashlib
import json

from aethron._json_bounds import check

from .campaign import LIGHTING, SENSORS, _inputs
from .evidence import EVIDENCE, _enum, _hash, _keys, _pairs, _parse_integer


def _require(condition):
    if not condition:
        raise ValueError("invalid_qualification_domain")


def _key(profile):
    sensors = profile["required_sensors"]
    return (
        profile["lighting"],
        None if sensors is None else tuple(sorted(sensors)),
        profile["evidence"],
    )


def _schema(doc):
    _keys(doc, "version kind rig_sha256 profiles")
    _require(type(doc["version"]) is int and doc["version"] == 1)
    _enum(doc["kind"], ("qualification_domain",))
    _hash(doc["rig_sha256"])
    _require(type(doc["profiles"]) is list and len(doc["profiles"]) <= 16)
    keys = []
    for profile in doc["profiles"]:
        _keys(profile, "lighting required_sensors evidence")
        for key, allowed in (("lighting", LIGHTING), ("evidence", EVIDENCE)):
            if profile[key] is not None:
                _enum(profile[key], allowed)
        sensors = profile["required_sensors"]
        if sensors is not None:
            _require(type(sensors) is list and 1 <= len(sensors) <= 5)
            for sensor in sensors:
                _enum(sensor, SENSORS)
            _require(len(set(sensors)) == len(sensors))
        keys.append(_key(profile))
    _require(len(set(keys)) == len(keys))
    return keys


def validate(plan_bytes, domain_bytes):
    """Check exact pins and bidirectional tuple coverage without interpreting authority."""
    try:
        plan, _ = _inputs(plan_bytes, [])
        _require(check(domain_bytes))
        doc = json.loads(
            domain_bytes.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_int=_parse_integer,
            parse_constant=lambda _: _require(False),
        )
        keys = _schema(doc)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid_qualification_domain") from None

    digest = hashlib.sha256(domain_bytes).hexdigest()
    findings = set()
    if digest != plan["domain_sha256"]:
        findings.add("domain_digest_mismatch")
    if doc["rig_sha256"] != plan["rig_sha256"]:
        findings.add("domain_rig_mismatch")
    if not keys:
        findings.add("domain_profiles_missing")
    known = {key: index for index, key in enumerate(keys) if None not in key}
    counts = [0] * len(keys)
    cases = []
    for index, case in enumerate(plan["cases"]):
        match = known.get(_key(case))
        if match is None:
            findings.add("domain_case_unmatched")
        else:
            counts[match] += 1
        cases.append({"case_index": index, "profile_index": match})
    profiles = []
    for index, key in enumerate(keys):
        unknown = None in key
        if unknown:
            findings.add("domain_profile_unknown")
        elif counts[index] == 0:
            findings.add("domain_profile_uncovered")
        profiles.append(
            {
                "profile_index": index,
                "status": "unknown" if unknown else "unverified",
                "matched_case_count": counts[index],
            }
        )
    return {
        "version": 1,
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "domain_sha256": digest,
        "findings": sorted(findings),
        "domain_declaration_checks_passed": not findings,
        "content_status": "incomplete" if findings else "consistent_unverified",
        "cases": cases,
        "profiles": profiles,
        "domain_verified": False,
        "artifact_authenticity_verified": False,
        "physical_qualification_passed": False,
        "human_review_status": "unverified",
    }
