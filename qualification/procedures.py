"""Validate non-executing checklist declarations, never procedure approval."""

import hashlib
import json

from aethron._json_bounds import check

from .campaign import _inputs
from .evidence import KINDS, _enum, _hash, _keys, _pairs, _parse_integer, _token


def _require(condition):
    if not condition:
        raise ValueError("invalid_qualification_procedure")


def _schema(doc):
    _keys(doc, "version kind rig_sha256 domain_sha256 cases")
    _require(type(doc["version"]) is int and doc["version"] == 1)
    _enum(doc["kind"], ("qualification_checklist",))
    _hash(doc["rig_sha256"])
    _hash(doc["domain_sha256"])
    _require(type(doc["cases"]) is list and len(doc["cases"]) <= 16)
    seen = set()
    for case in doc["cases"]:
        _keys(case, "case_id checks")
        _token(case["case_id"])
        _require(case["case_id"] not in seen)
        seen.add(case["case_id"])
        _require(type(case["checks"]) is list and len(case["checks"]) <= 3)
        kinds = set()
        for entry in case["checks"]:
            _keys(entry, "kind specification_sha256")
            _enum(entry["kind"], KINDS)
            _require(entry["kind"] not in kinds)
            kinds.add(entry["kind"])
            if entry["specification_sha256"] is not None:
                _hash(entry["specification_sha256"])


def validate(plan_bytes, procedure_bytes):
    """Compare exact bytes and checklist coverage; do not resolve method digests."""
    try:
        plan, _ = _inputs(plan_bytes, [])
        _require(check(procedure_bytes))
        doc = json.loads(
            procedure_bytes.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_int=_parse_integer,
            parse_constant=lambda _: _require(False),
        )
        _schema(doc)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("invalid_qualification_procedure") from None

    digest = hashlib.sha256(procedure_bytes).hexdigest()
    findings = set()
    if digest != plan["procedure_sha256"]:
        findings.add("procedure_digest_mismatch")
    for key in ("rig", "domain"):
        if doc[key + "_sha256"] != plan[key + "_sha256"]:
            findings.add("procedure_" + key + "_mismatch")

    planned = {case["id"] for case in plan["cases"]}
    states = {}
    for case in doc["cases"]:
        state = dict.fromkeys(KINDS, "missing")
        for entry in case["checks"]:
            state[entry["kind"]] = (
                "unknown" if entry["specification_sha256"] is None else "unverified"
            )
        states[case["case_id"]] = state
        if "missing" in state.values():
            findings.add("procedure_check_missing")
        if "unknown" in state.values():
            findings.add("procedure_specification_unknown")
    if states.keys() - planned:
        findings.add("procedure_case_unplanned")
    if planned - states.keys():
        findings.update(("procedure_case_missing", "procedure_check_missing"))

    return {
        "version": 1,
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "procedure_sha256": digest,
        "findings": sorted(findings),
        "procedure_declaration_checks_passed": not findings,
        "content_status": "incomplete" if findings else "consistent_unverified",
        "cases": [
            {
                "case_index": index,
                "checks": states.get(case["id"], dict.fromkeys(KINDS, "missing")),
            }
            for index, case in enumerate(plan["cases"])
        ],
        "procedure_verified": False,
        "specification_bytes_verified": False,
        "artifact_authenticity_verified": False,
        "physical_qualification_passed": False,
        "human_review_status": "unverified",
    }
