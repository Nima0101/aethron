"""Pinned offline task descriptions; no execution, authorization or scheduling."""

import hashlib
from dataclasses import dataclass, field
from typing import Optional

from .passports import (
    _HEX,
    _canonical,
    _enum,
    _integer,
    _interval,
    _object,
    _parse,
    _require,
    _token,
    _unique_tokens,
)


def _task(value):
    _object(
        value,
        "version task_id kind subject_sha256 passport_sha256 policy_sha256 "
        "evidence_sha256 issued_at expires_at max_evidence_bytes motion_authority",
    )
    _integer(value["version"], 1)
    _require(value["version"] == 1 and value["motion_authority"] is False)
    _token(value["task_id"])
    _enum(value["kind"], {"passport.verify.v1", "evidence.bind.v1"})
    for key in ("subject_sha256", "passport_sha256", "policy_sha256"):
        _token(value[key], _HEX)
    _interval(value["issued_at"], value["expires_at"], 300)
    _integer(value["max_evidence_bytes"])
    _unique_tokens(value["evidence_sha256"], 16, minimum=0, digests=True)
    if value["kind"] == "passport.verify.v1":
        _require(not value["evidence_sha256"] and value["max_evidence_bytes"] == 0)
    else:
        _require(bool(value["evidence_sha256"]) and 1 <= value["max_evidence_bytes"] <= 1048576)
    return value


def canonicalize_task(raw: bytes) -> bytes:
    """Validate the closed shape and produce portable canonical task bytes."""
    try:
        return _canonical(_task(_parse(raw)))
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ValueError("invalid_task") from None


@dataclass(frozen=True)
class TaskValidation:
    status: str
    reason: str
    task_sha256: Optional[str] = None
    expires_at: Optional[int] = None
    execution_authority: bool = field(default=False, init=False)
    motion_authority: bool = field(default=False, init=False)
    evidence_verified: bool = field(default=False, init=False)


def validate_task(
    raw: bytes,
    *,
    expected_task_sha256: str,
    expected_subject_sha256: str,
    now_s: int,
    minimum_time_s: int,
) -> TaskValidation:
    """Validate against externally authenticated pins and caller-trusted time.

    Stateless and I/O-free: no replay protection or referenced-artifact verification.
    """
    try:
        _token(expected_task_sha256, _HEX)
        _token(expected_subject_sha256, _HEX)
        _integer(now_s)
        _integer(minimum_time_s)
        if now_s < minimum_time_s:
            return TaskValidation("rejected", "time_rollback")
        task = _task(_parse(raw))
        _require(_canonical(task) == raw)
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_task_sha256:
            return TaskValidation("rejected", "task_mismatch")
        if task["subject_sha256"] != expected_subject_sha256:
            return TaskValidation("rejected", "subject_mismatch")
        if not task["issued_at"] <= now_s < task["expires_at"]:
            return TaskValidation("rejected", "task_not_current")
        return TaskValidation("validated", "description_matches", digest, task["expires_at"])
    except (ValueError, TypeError, KeyError, RecursionError):
        return TaskValidation("rejected", "invalid_input")
