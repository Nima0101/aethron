"""Authenticate a bounded private snapshot before creating rollout bookkeeping."""

import hashlib
import os
import stat
import tempfile
from collections.abc import Callable
from itertools import islice
from pathlib import Path

from ._regular_file import regular_reader
from .fleet_floors import FleetFloorStore
from .fleet_policy import load_fleet_policy
from .fleet_rollout import RolloutJournal

_LIMITS = {
    "manifest.json": 8192,
    "manifest.sig": 64,
    "fleet-policy.json": 2048,
    "fleet-artifact.bin": 8 * 1024 * 1024,
}


def _copy_snapshot(bundle, snapshot):
    if not stat.S_ISDIR(bundle.lstat().st_mode):
        raise ValueError()
    with os.scandir(bundle) as entries:
        if {entry.name for entry in islice(entries, 5)} != set(_LIMITS):
            raise ValueError()
    pins = {}
    for name, limit in _LIMITS.items():
        digest = hashlib.sha256()
        with regular_reader(bundle / name, limit) as (source, remaining):
            with (snapshot / name).open("xb") as destination:
                while remaining:
                    chunk = source.read(min(65536, remaining))
                    if not chunk:
                        raise ValueError()
                    remaining -= len(chunk)
                    digest.update(chunk)
                    destination.write(chunk)
                if source.read(1):
                    raise ValueError()
        pins[name] = digest.hexdigest()
    return pins


def _time(value, minimum, maximum=2**53 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError()
    return value


def create_rollout_plan(
    bundle: Path,
    public_key: Path,
    *,
    journal_path: Path,
    floor_store: FleetFloorStore,
    clock: Callable[[], int],
) -> RolloutJournal:
    """Create inert bookkeeping; never install or return execution authority.

    Trusted caller controls the clock, pinned key and local store directories.
    Floor commits are never undone if subsequent journal creation fails.
    """
    try:
        floors = floor_store.read()
        started = _time(clock(), floors.minimum_time_s)
        with tempfile.TemporaryDirectory(prefix="aethron-fleet-plan-") as temporary:
            snapshot = Path(temporary)
            pins = _copy_snapshot(Path(bundle), snapshot)
            # The verifier sees only our bounded private copy, including the
            # exact policy and artifact bytes whose digests are recorded below.
            policy = load_fleet_policy(
                snapshot,
                Path(public_key),
                now_unix_s=started,
                minimum_version=floors.minimum_version,
            )
            verified_at = _time(clock(), started, policy.expires_unix_s - 1)
        # Remove the temporary snapshot before any durable success state. The
        # private copy was evidence for pins, not a retained deployment payload.
        floor_store.advance(minimum_version=policy.bundle_version, minimum_time_s=verified_at)
        created_at = _time(clock(), verified_at, policy.expires_unix_s - 1)
        journal = RolloutJournal.initialize(
            journal_path,
            policy_sha256=pins["fleet-policy.json"],
            artifact_sha256=pins["fleet-artifact.bin"],
            version=policy.bundle_version,
            slot_count=policy.slot_count,
            batch_size=policy.batch_size,
            not_before_unix_s=policy.not_before_unix_s,
            expires_unix_s=policy.expires_unix_s,
            now_unix_s=created_at,
        )
        # Journal creation may block past expiry. Preserve both durable stores
        # on late rejection; the caller must reconcile the existing journal.
        _time(clock(), created_at, policy.expires_unix_s - 1)
        return journal
    except (OSError, ValueError, TypeError, RuntimeError, StopIteration):
        raise ValueError("invalid_fleet_plan") from None


def claim_rollout_wave(
    bundle: Path,
    public_key: Path,
    *,
    journal: RolloutJournal,
    floor_store: FleetFloorStore,
    clock: Callable[[], int],
    expected_revision: int,
    provisioning: bool = False,
) -> tuple[int, ...]:
    """Reverify before a synthetic reservation; never execute an artifact.

    Return only after both commits. A failed final floor commit can leave
    unresolved reservations; never automatically retry or erase those slots.
    """
    try:
        if type(provisioning) is not bool:
            raise ValueError()
        recorded = journal.snapshot()
        floors = floor_store.read()
        started = _time(clock(), max(floors.minimum_time_s, recorded.last_time_s))
        with tempfile.TemporaryDirectory(prefix="aethron-fleet-claim-") as temporary:
            snapshot = Path(temporary)
            pins = _copy_snapshot(Path(bundle), snapshot)
            policy = load_fleet_policy(
                snapshot,
                Path(public_key),
                now_unix_s=started,
                minimum_version=floors.minimum_version,
            )
            if (
                pins["fleet-policy.json"] != recorded.policy_sha256
                or pins["fleet-artifact.bin"] != recorded.artifact_sha256
                or policy.bundle_version != recorded.version
                or policy.slot_count != recorded.slot_count
                or policy.batch_size != recorded.batch_size
                or policy.not_before_unix_s != recorded.not_before_unix_s
                or policy.expires_unix_s != recorded.expires_unix_s
                or (provisioning and not policy.allow_initial_provisioning)
            ):
                raise ValueError()
            verified_at = _time(clock(), started, policy.expires_unix_s - 1)
        # Consistent lock order: floor writer first, then journal writer.
        # No public claim is returned from inside this provisional transaction.
        with floor_store.guarded_advance(
            minimum_version=policy.bundle_version, minimum_time_s=verified_at
        ):
            claimed_at = _time(clock(), verified_at, policy.expires_unix_s - 1)
            slots = journal.claim(expected_revision=expected_revision, now_unix_s=claimed_at)
            _time(clock(), claimed_at, policy.expires_unix_s - 1)
        return slots
    except (OSError, ValueError, TypeError, RuntimeError, StopIteration):
        raise ValueError("invalid_fleet_claim") from None
