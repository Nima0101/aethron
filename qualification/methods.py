"""Bind non-executing method rule declarations without approving procedures."""

import hashlib
import json

from aethron._json_bounds import check

from .evidence import _enum, _hash, _integer, _keys, _pairs, _parse_integer, _token
from .procedures import validate as validate_procedure

MAX_METHODS = 48
MAX_METHOD_BYTES = 65536

# These describe existing v1 gates; they do not configure runtime execution.
RULES = {
    "calibration": {
        "rig_binding": "exact",
        "clock_domain": "capture",
        "interval": "entire_capture",
    },
    "clock": {
        "rig_binding": "exact",
        "clock_domain": "capture",
        "within_capture": "required",
        "max_age_ms": 100,
        "reference_skew_ms": 50,
        "pair_skew_ms": 50,
    },
    "environment": {
        "rig_binding": "exact",
        "clock_domain": "capture",
        "within_capture": "required",
        "max_age_ms": 100,
        "lighting": "campaign_case",
    },
}


def _require(condition):
    if not condition:
        raise ValueError("invalid_qualification_methods")


def _content(raw):
    _require(check(raw))
    doc = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_pairs,
        parse_int=_parse_integer,
        parse_constant=lambda _: _require(False),
    )
    _keys(doc, "version kind check rules")
    _require(type(doc["version"]) is int and doc["version"] == 1)
    _enum(doc["kind"], ("qualification_declaration_method",))
    _enum(doc["check"], RULES)
    expected = RULES[doc["check"]]
    _keys(doc["rules"], " ".join(expected))
    findings = set()
    for key, target in expected.items():
        value = doc["rules"][key]
        if value is None:
            findings.add("method_rule_unknown")
            continue
        if type(target) is int:
            _integer(value)
        else:
            _token(value)
        if value != target:
            findings.add("method_rule_mismatch")
    return doc["check"], findings


def verify(plan_bytes, procedure_bytes, methods):
    """Preserve checklist, binding and content failures independently."""
    try:
        procedure = validate_procedure(plan_bytes, procedure_bytes)
        _require(type(methods) is dict and len(methods) <= MAX_METHODS)
        supplied = methods.copy()
        _require(len(supplied) <= MAX_METHODS)
        for digest, raw in supplied.items():
            _hash(digest)
            _require(type(raw) is bytes and len(raw) <= MAX_METHOD_BYTES)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid_qualification_methods") from None

    # The identical immutable checklist already passed strict admission.
    doc = json.loads(procedure_bytes)
    references = {}
    for case in doc["cases"]:
        for entry in case["checks"]:
            digest = entry["specification_sha256"]
            if digest is not None:
                references.setdefault(digest, set()).add(entry["kind"])
    actual = {key: hashlib.sha256(raw).hexdigest() for key, raw in supplied.items()}
    byte_findings = set()
    if not references:
        byte_findings.add("method_references_empty")
    if references.keys() - supplied.keys():
        byte_findings.add("method_missing")
    if supplied.keys() - references.keys():
        byte_findings.add("method_unreferenced")
    if any(key != digest for key, digest in actual.items()):
        byte_findings.add("method_digest_mismatch")
    findings = byte_findings.copy()
    for digest, raw in supplied.items():
        try:
            kind, local = _content(raw)
        except (ValueError, UnicodeError, RecursionError):
            findings.add("method_invalid")
            continue
        findings.update(local)
        if digest in references and references[digest] != {kind}:
            findings.add("method_check_mismatch")
    commitment = hashlib.sha256(
        b"aethron.qualification.methods.v1\0"
        + json.dumps(sorted(actual.items()), separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    return {
        "version": 1,
        "procedure": procedure,
        "methods_sha256": commitment,
        "method_counts": {
            "referenced": len(references),
            "supplied": len(supplied),
            "supplied_bytes": sum(map(len, supplied.values())),
        },
        "method_findings": sorted(findings),
        "method_bytes_verified": not byte_findings,
        "software_checks_passed": not findings and procedure["procedure_declaration_checks_passed"],
        "method_verified": False,
        "artifact_authenticity_verified": False,
        "physical_qualification_passed": False,
        "human_review_status": "unverified",
    }
