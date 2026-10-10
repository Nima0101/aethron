"""Bounded offline authentication of self-declared software capability statements.

No result grants authority or qualifies evidence. Trust policy, revision/time floors
and expected artifact digest must come from the caller's authenticated configuration.
"""

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Optional

from ._json_bounds import check as check_bounds

PAYLOAD_TYPE = "application/vnd.aethron.capability-passport.v1+json"
CAPABILITIES = frozenset({"perception.direct.v3", "presence.coarse.v2", "evidence.offline.v1"})
MAX_INTEGER = 2**53 - 1
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_HEX = re.compile(r"[a-f0-9]{64}")


def _require(condition):
    if not condition:
        raise ValueError("invalid_passport")


def _object(value, fields):
    _require(type(value) is dict and set(value) == set(fields.split()))


def _integer(value, minimum=0):
    _require(type(value) is int and minimum <= value <= MAX_INTEGER)


def _token(value, pattern=_IDENTIFIER):
    _require(type(value) is str and pattern.fullmatch(value) is not None)


def _enum(value, allowed):
    _require(type(value) is str and value in allowed)


def _list(value, maximum, minimum=1):
    _require(type(value) is list and minimum <= len(value) <= maximum)


def _unique_tokens(value, maximum, *, minimum=1, digests=False, allowed=None):
    _list(value, maximum, minimum)
    for item in value:
        _token(item, _HEX if digests else _IDENTIFIER)
        if allowed is not None:
            _enum(item, allowed)
    _require(len(value) == len(set(value)))
    return set(value)


def _pairs(items):
    result = {}
    for key, value in items:
        _require(key not in result)
        result[key] = value
    return result


def _not_integer(_value):
    raise ValueError("invalid_passport")


def _parse(raw):
    _require(check_bounds(raw))
    # Decode explicitly: json.loads(bytes) otherwise accepts UTF-16/UTF-32.
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_pairs,
        parse_float=_not_integer,
        parse_constant=_not_integer,
    )


def _interval(start, end, maximum=None):
    _integer(start)
    _integer(end)
    _require(start < end)
    if maximum is not None:
        _require(end - start <= maximum)


def _payload(value):
    _object(
        value,
        "version passport_id issuer subject_sha256 issued_at expires_at "
        "assurance motion_authority capabilities evidence",
    )
    _integer(value["version"], 1)
    _require(value["version"] == 1)
    _token(value["passport_id"])
    _token(value["issuer"])
    _token(value["subject_sha256"], _HEX)
    _interval(value["issued_at"], value["expires_at"], 86400)
    _require(value["assurance"] == "self_declared" and value["motion_authority"] is False)
    _list(value["evidence"], 16)
    evidence = set()
    for item in value["evidence"]:
        _object(item, "sha256 kind outcome")
        _token(item["sha256"], _HEX)
        _require(item["sha256"] not in evidence)
        evidence.add(item["sha256"])
        _enum(item["kind"], {"synthetic", "recorded", "external_unverified"})
        _enum(item["outcome"], {"passed", "failed", "unknown"})
    _list(value["capabilities"], 3)
    names, references = set(), set()
    for item in value["capabilities"]:
        _object(item, "name evidence_sha256")
        _enum(item["name"], CAPABILITIES)
        _require(item["name"] not in names)
        names.add(item["name"])
        references.update(_unique_tokens(item["evidence_sha256"], 16, digests=True))
    _require(references == evidence)
    return value


def _canonical(value):
    # The schema permits only ASCII strings, booleans and safe integers. No float
    # serialization, Unicode ordering or normalization is delegated to json.dumps.
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def canonicalize(payload: bytes) -> bytes:
    """Validate the closed v1 schema and return its canonical JSON bytes."""
    try:
        return _canonical(_payload(_parse(payload)))
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ValueError("invalid_passport") from None


def pae(payload: bytes) -> bytes:
    """DSSE pre-authentication encoding for this fixed payload type."""
    _require(type(payload) is bytes and len(payload) <= 65536)
    kind = PAYLOAD_TYPE.encode("ascii")
    return (
        b"DSSEv1 "
        + str(len(kind)).encode("ascii")
        + b" "
        + kind
        + b" "
        + (str(len(payload)).encode("ascii") + b" " + payload)
    )


def _base64(value, size=None):
    _require(type(value) is str and len(value) <= 65536)
    raw = base64.b64decode(value, validate=True)
    _require(base64.b64encode(raw).decode("ascii") == value)
    if size is not None:
        _require(len(raw) == size)
    return raw


def _policy(value):
    _object(
        value,
        "version revision issued_at expires_at keys revoked_passports "
        "revoked_keys revoked_evidence",
    )
    _integer(value["version"], 1)
    _require(value["version"] == 1)
    _integer(value["revision"], 1)
    _interval(value["issued_at"], value["expires_at"], 3600)
    _unique_tokens(value["revoked_passports"], 256, minimum=0)
    _unique_tokens(value["revoked_keys"], 256, minimum=0, digests=True)
    _unique_tokens(value["revoked_evidence"], 256, minimum=0, digests=True)
    _list(value["keys"], 16)
    keys = {}
    for key in value["keys"]:
        _object(key, "key_id issuer public_key not_before expires_at capabilities")
        _token(key["key_id"], _HEX)
        _token(key["issuer"])
        _token(key["public_key"], _HEX)
        _require(key["key_id"] == hashlib.sha256(bytes.fromhex(key["public_key"])).hexdigest())
        _require(key["key_id"] not in keys)
        _interval(key["not_before"], key["expires_at"])
        _unique_tokens(key["capabilities"], 3, allowed=CAPABILITIES)
        keys[key["key_id"]] = key
    return value, keys


@dataclass(frozen=True)
class VerificationResult:
    """Authentication only; never a capability grant or evidence qualification."""

    status: str
    reason: str
    payload_sha256: Optional[str] = None
    policy_revision: Optional[int] = None
    expires_at: Optional[int] = None

    @property
    def motion_authority(self):
        return False

    @property
    def evidence_verified(self):
        return False


def _rejected(reason):
    return VerificationResult("rejected", reason)


def verify(
    envelope: bytes,
    policy: bytes,
    *,
    now_s: int,
    minimum_time_s: int,
    minimum_policy_revision: int,
    expected_subject_sha256: str,
) -> VerificationResult:
    """Authenticate using caller-provisioned policy/time/floors; perform no I/O.

    The caller must preserve accepted time/revision high-water marks across restarts.
    Expiry/revocation reflect only the provided snapshot, not global live status.
    """
    try:
        _integer(now_s)
        _integer(minimum_time_s)
        _integer(minimum_policy_revision, 1)
        _token(expected_subject_sha256, _HEX)
        if now_s < minimum_time_s:
            return _rejected("time_rollback")
        trust, keys = _policy(_parse(policy))
        if trust["revision"] < minimum_policy_revision:
            return _rejected("policy_rollback")
        if not trust["issued_at"] <= now_s < trust["expires_at"]:
            return _rejected("policy_not_current")
        outer = _parse(envelope)
        _object(outer, "payloadType payload signatures")
        _require(outer["payloadType"] == PAYLOAD_TYPE)
        _list(outer["signatures"], 1)
        signature = outer["signatures"][0]
        _object(signature, "keyid sig")
        _token(signature["keyid"], _HEX)
        sig = _base64(signature["sig"], 64)
        raw = _base64(outer["payload"])
        statement = _payload(_parse(raw))
        _require(raw == _canonical(statement))
        if statement["subject_sha256"] != expected_subject_sha256:
            return _rejected("subject_mismatch")
        if not statement["issued_at"] <= now_s < statement["expires_at"]:
            return _rejected("passport_not_current")
        key_id = signature["keyid"]
        if key_id not in keys:
            return _rejected("untrusted_key")
        if (
            key_id in trust["revoked_keys"]
            or statement["passport_id"] in trust["revoked_passports"]
            or any(e["sha256"] in trust["revoked_evidence"] for e in statement["evidence"])
        ):
            return _rejected("revoked")
        key = keys[key_id]
        if (
            not key["not_before"]
            <= statement["issued_at"]
            < statement["expires_at"]
            <= (key["expires_at"])
        ):
            return _rejected("key_not_current")
        if key["issuer"] != statement["issuer"] or any(
            item["name"] not in key["capabilities"] for item in statement["capabilities"]
        ):
            return _rejected("scope_mismatch")
        try:
            from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except ImportError:
            return _rejected("crypto_unavailable")
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(key["public_key"])).verify(
                sig, pae(raw)
            )
        except InvalidSignature:
            return _rejected("invalid_signature")
        except UnsupportedAlgorithm:
            return _rejected("crypto_unavailable")
        return VerificationResult(
            "authenticated",
            "signature_verified",
            hashlib.sha256(raw).hexdigest(),
            trust["revision"],
            min(statement["expires_at"], trust["expires_at"]),
        )
    except (ValueError, TypeError, KeyError, RecursionError, binascii.Error):
        return _rejected("invalid_input")
