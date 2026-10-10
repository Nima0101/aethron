"""Signed local fleet-policy admission; no transport, installation or actuation."""

import base64
import hashlib
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..config import strict_json
from ._regular_file import regular_reader
from .fleet_floors import FleetFloorStore
from .updates import verify_bundle

_FIELDS = frozenset(
    (
        "schema_version",
        "bundle_version",
        "not_before_unix_s",
        "expires_unix_s",
        "slot_count",
        "batch_size",
        "allow_initial_provisioning",
    )
)


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _ed25519_public_key(path: Path) -> bytes:
    """Admit only the fixed RFC 8410 Ed25519 SPKI shape, not generic ASN.1."""
    with regular_reader(path, 1024) as (stream, _):
        raw = stream.read(1025)
    lines = raw.splitlines()
    if (
        len(raw) > 1024
        or len(lines) < 3
        or lines[0] != b"-----BEGIN PUBLIC KEY-----"
        or lines[-1] != b"-----END PUBLIC KEY-----"
    ):
        raise ValueError()
    encoded = b"".join(lines[1:-1])
    der = base64.b64decode(encoded, validate=True)
    # SEQUENCE { SEQUENCE { OID 1.3.101.112 }, BIT STRING (0 unused bits, 32 bytes) }.
    # Parameters must be absent. No alternate algorithm, trailing DER or BER lengths.
    if (
        len(der) != 44
        or der[:12] != bytes.fromhex("302a300506032b6570032100")
        or base64.b64encode(der) != encoded
    ):
        raise ValueError()
    return b"-----BEGIN PUBLIC KEY-----\n" + encoded + b"\n-----END PUBLIC KEY-----\n"


@dataclass(frozen=True)
class FleetPolicy:
    """Configuration only: execution must reverify trust, time and rollback state."""

    bundle_version: int
    not_before_unix_s: int
    expires_unix_s: int
    slot_count: int
    batch_size: int
    allow_initial_provisioning: bool


def load_fleet_policy(
    bundle: Path, public_key: Path, *, now_unix_s: int, minimum_version: int
) -> FleetPolicy:
    """Caller owns trusted UTC, the pinned key and the durable minimum version."""
    try:
        if not _integer(now_unix_s, 0, 2**53 - 1) or not _integer(minimum_version, 1, 2**31 - 1):
            raise ValueError()
        bundle = Path(bundle)
        key = _ed25519_public_key(Path(public_key))
        # Bind the admitted algorithm and bytes to the verifier's actual input.
        # Reading the caller's key path again would reopen the selection race.
        with tempfile.TemporaryDirectory(prefix="aethron-fleet-key-") as temporary:
            pinned_key = Path(temporary) / "public.pem"
            pinned_key.write_bytes(key)
            manifest = verify_bundle(bundle, pinned_key)
        expected = manifest["files"]["fleet-policy.json"]
        with regular_reader(bundle / "fleet-policy.json", 2048) as (stream, _):
            raw = stream.read(2049)
        # The directory is not a snapshot. Bind exactly the bytes we parse to
        # the authenticated manifest even if the payload changed after verify.
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError()
        value = strict_json(raw.decode("utf-8"), 2048)
        if (
            type(value) is not dict
            or value.keys() != _FIELDS
            or not _integer(value["schema_version"], 1, 1)
            or not _integer(value["bundle_version"], minimum_version, 2**31 - 1)
            or value["bundle_version"] != manifest["version"]
            or not _integer(value["not_before_unix_s"], 0, 2**53 - 1)
            or not _integer(value["expires_unix_s"], 0, 2**53 - 1)
            or not value["not_before_unix_s"] <= now_unix_s < value["expires_unix_s"]
            or not 1 <= value["expires_unix_s"] - value["not_before_unix_s"] <= 86400
            or not _integer(value["slot_count"], 1, 1024)
            or not _integer(value["batch_size"], 1, min(32, value["slot_count"]))
            or type(value["allow_initial_provisioning"]) is not bool
        ):
            raise ValueError()
        return FleetPolicy(**{key: item for key, item in value.items() if key != "schema_version"})
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise ValueError("invalid_fleet_policy") from None


def admit_fleet_policy(
    bundle: Path,
    public_key: Path,
    *,
    floor_store: FleetFloorStore,
    clock: Callable[[], int],
) -> FleetPolicy:
    """Commit authenticated floors before returning point-in-time configuration.

    Trusted caller supplies the pinned key, protected store and trusted UTC
    source. This is not a transferable or lasting deployment authorization.
    """
    try:
        floors = floor_store.read()
        started = clock()
        if not _integer(started, floors.minimum_time_s, 2**53 - 1):
            raise ValueError()
        policy = load_fleet_policy(
            bundle, public_key, now_unix_s=started, minimum_version=floors.minimum_version
        )
        finished = clock()
        if (
            not _integer(finished, started, 2**53 - 1)
            or not policy.not_before_unix_s <= finished < policy.expires_unix_s
        ):
            raise ValueError()
        # advance rereads both floors under its writer transaction. A competing
        # admission can invalidate this candidate after signature verification.
        floor_store.advance(minimum_version=policy.bundle_version, minimum_time_s=finished)
        return policy
    except (OSError, ValueError, TypeError, RuntimeError, StopIteration):
        raise ValueError("invalid_fleet_admission") from None
