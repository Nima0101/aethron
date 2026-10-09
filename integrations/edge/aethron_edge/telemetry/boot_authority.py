"""Explicit offline clock policy. SPDX-License-Identifier: GPL-3.0-only.

A trusted local clock/provisioner is required. Kernel time alone is not evidence
of an accurate RTC. This module neither receives packets nor resets replay state.
"""

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .provisioning import _BOOT, current_boot_id
from .signing import (
    MAX_TIMESTAMP,
    SigningTrust,
    _connect,
    _identity,
    _private_parent,
    _scope,
    provision_replay,
)

MAVLINK_EPOCH_NS = 1_420_070_400_000_000_000  # 2015-01-01T00:00:00Z
MAX_SAMPLE_NS = 1_000_000


@dataclass(frozen=True)
class BootClockPolicy:
    key: bytes = field(repr=False)
    system_id: int
    component_id: int
    link_id: int
    not_before_unix_ns: int
    not_after_unix_ns: int
    lease_ns: int
    drift_budget_ns: int

    def __post_init__(self):
        if (
            type(self.key) is not bytes
            or len(self.key) != 32
            or any(
                type(x) is not int or not 1 <= x <= 255 for x in (self.system_id, self.component_id)
            )
            or type(self.link_id) is not int
            or not 0 <= self.link_id <= 255
            or any(
                type(x) is not int
                for x in (
                    self.not_before_unix_ns,
                    self.not_after_unix_ns,
                    self.lease_ns,
                    self.drift_budget_ns,
                )
            )
            or not MAVLINK_EPOCH_NS
            <= self.not_before_unix_ns
            < self.not_after_unix_ns
            < MAVLINK_EPOCH_NS + MAX_TIMESTAMP * 10_000
            or not 1 <= self.lease_ns <= self.not_after_unix_ns - self.not_before_unix_ns
            or not MAX_SAMPLE_NS <= self.drift_budget_ns <= 1_000_000_000
        ):
            raise ValueError("invalid_boot_clock_policy")

    @property
    def scope(self):
        return _scope(
            SigningTrust(self.key, self.link_id, 0, 0, 1), self.system_id, self.component_id
        )

    @property
    def digest(self):
        values = [
            self.scope,
            self.not_before_unix_ns,
            self.not_after_unix_ns,
            self.lease_ns,
            self.drift_budget_ns,
        ]
        return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


@contextmanager
def _journal(path, policy):
    if type(policy) is not BootClockPolicy:
        raise ValueError("invalid_policy")
    path = Path(path).absolute()
    identity = _identity(path)
    connection = _connect(path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute("SELECT id, scope, timestamp FROM replay").fetchmany(2)
        if (
            len(rows) != 1
            or rows[0][0] != 1
            or rows[0][1] != policy.scope
            or type(rows[0][2]) is not int
            or not 0 <= rows[0][2] <= MAX_TIMESTAMP
        ):
            raise ValueError("invalid_replay_state")
        yield connection, rows[0][2]
        if _identity(path) != identity:
            raise ValueError("replaced_journal")
        connection.commit()
    finally:
        connection.close()


def provision_boot_authority(path, policy):
    """Explicit one-time binding of an existing replay journal to clock policy."""
    try:
        with _journal(path, policy) as (connection, _):
            connection.execute(
                "CREATE TABLE boot_authority (id INTEGER PRIMARY KEY CHECK(id=1), "
                "policy TEXT NOT NULL, boot TEXT, wall INTEGER NOT NULL, "
                "issued INTEGER NOT NULL, expires INTEGER NOT NULL, "
                "floor INTEGER NOT NULL, sample INTEGER NOT NULL, revoked INTEGER NOT NULL, "
                "last_wall INTEGER NOT NULL, checked INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT INTO boot_authority VALUES (1, ?, NULL, 0, 0, 0, 0, 0, 0, 0, 0)",
                (policy.digest,),
            )
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
        raise ValueError("invalid_boot_authority") from None


def _sample(monotonic, realtime):
    before, wall, after = monotonic(), realtime(), monotonic()
    if (
        any(type(x) is not int or not 0 <= x < 2**63 for x in (before, wall, after))
        or not 0 <= after - before <= MAX_SAMPLE_NS
    ):
        raise ValueError("invalid_clock_sample")
    return before, wall, after - before


def _record(connection, policy):
    rows = connection.execute(
        "SELECT id, policy, boot, wall, issued, expires, floor, sample, revoked, last_wall, checked "
        "FROM boot_authority"
    ).fetchmany(2)
    if len(rows) != 1 or rows[0][0] != 1 or rows[0][1] != policy.digest:
        raise ValueError("invalid_policy_binding")
    _, _, boot, wall, issued, expires, floor, sample, revoked, last_wall, checked = rows[0]
    if any(
        type(x) is not int
        for x in (wall, issued, expires, floor, sample, revoked, last_wall, checked)
    ) or revoked not in (0, 1):
        raise ValueError("invalid_grant_record")
    if boot is None:
        if any((wall, issued, expires, floor, sample, revoked, last_wall, checked)):
            raise ValueError("invalid_empty_record")
    elif (
        type(boot) is not str
        or not _BOOT.fullmatch(boot)
        or not policy.not_before_unix_ns <= wall < policy.not_after_unix_ns
        or not 0 <= issued < expires < 2**63
        or expires != issued + min(policy.lease_ns, policy.not_after_unix_ns - wall)
        or floor != (wall - MAVLINK_EPOCH_NS) // 10_000
        or not 0 <= sample <= MAX_SAMPLE_NS
        or not wall <= last_wall < 2**63
        or not issued <= checked < 2**63
    ):
        raise ValueError("invalid_grant_record")
    return boot, wall, issued, expires, floor, sample, revoked, last_wall, checked


def issue_boot_trust(
    path, policy, *, monotonic=time.monotonic_ns, realtime=time.time_ns, boot_id=current_boot_id
):
    """Issue once per kernel boot; same-boot restarts reuse the persisted grant.

    Realtime is a caller-asserted trusted offline clock, not auto-attested UTC.
    Same-boot drift, rollback and expiry latch revocation in the journal. No lease
    renewal is provided. A different boot needs advancing time above replay state.
    """
    try:
        boot = boot_id()
        if type(boot) is not str or not _BOOT.fullmatch(boot):
            raise ValueError("invalid_boot")
        rejected = False
        with _journal(path, policy) as (connection, counter):
            (
                old_boot,
                old_wall,
                issued,
                expires,
                floor,
                old_sample,
                revoked,
                last_wall,
                checked,
            ) = _record(connection, policy)
            # Sample inside the transaction so concurrent callers cannot present
            # an older pre-lock clock sample after a later committed check.
            try:
                before, wall, sample = _sample(monotonic, realtime)
            except (ValueError, TypeError, OverflowError, OSError):
                rejected = True
                if boot == old_boot:
                    connection.execute("UPDATE boot_authority SET revoked=1 WHERE id=1")
            if not rejected:
                in_window = policy.not_before_unix_ns <= wall < policy.not_after_unix_ns
                if boot == old_boot:
                    consistent = (
                        before >= checked
                        and wall >= last_wall
                        and abs((wall - old_wall) - (before - issued)) + sample + old_sample
                        <= policy.drift_budget_ns
                    )
                    rejected = revoked or not in_window or before >= expires or not consistent
                    if consistent:
                        connection.execute(
                            "UPDATE boot_authority SET last_wall=?, checked=? WHERE id=1",
                            (wall, before),
                        )
                    if rejected:
                        connection.execute("UPDATE boot_authority SET revoked=1 WHERE id=1")
                else:
                    floor = (wall - MAVLINK_EPOCH_NS) // 10_000
                    rejected = (
                        not in_window
                        or floor <= counter
                        or (old_boot is not None and wall <= last_wall)
                    )
                    if not rejected:
                        issued = before
                        expires = before + min(policy.lease_ns, policy.not_after_unix_ns - wall)
                        SigningTrust(policy.key, policy.link_id, floor, issued, expires)
                        connection.execute(
                            "UPDATE boot_authority SET boot=?, wall=?, issued=?, expires=?, "
                            "floor=?, sample=?, revoked=0, last_wall=?, checked=? WHERE id=1",
                            (boot, wall, issued, expires, floor, sample, wall, before),
                        )
        if rejected:
            raise ValueError("clock_authority_rejected")
        now = monotonic()
        if type(now) is not int or not before <= now < expires:
            with _journal(path, policy) as (connection, _):
                _record(connection, policy)
                connection.execute(
                    "UPDATE boot_authority SET revoked=1 WHERE id=1 AND boot=? "
                    "AND issued=? AND floor=?",
                    (boot, issued, floor),
                )
            raise ValueError("authority_expired_during_commit")
        return SigningTrust(policy.key, policy.link_id, floor, issued, expires, boot_bound=True)
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
        raise ValueError("invalid_boot_authority") from None


class BootClockGuard:
    """Child-owned policy monitor; validation never renews the persisted grant.

    Status authority lasts at most100ms from the start of a successful check.
    Recheck every50ms of active polling. Blocking I/O cannot refresh that budget.
    """

    def __init__(self, path, policy, trust):
        if (
            type(policy) is not BootClockPolicy
            or type(trust) is not SigningTrust
            or not trust.boot_bound
            or trust.key != policy.key
            or trust.link_id != policy.link_id
        ):
            raise ValueError("invalid_clock_guard")
        self.path, self.policy, self.trust = path, policy, trust
        self.last_ns = trust.issued_ns
        self.checked_ns = None
        self.expires_ns = 0
        self.closed = False

    def check(self):
        try:
            now = time.monotonic_ns()
            if (
                self.closed
                or type(now) is not int
                or not self.last_ns <= now < self.trust.valid_until_ns
            ):
                raise ValueError()
            self.last_ns = now
            if self.checked_ns is None or now - self.checked_ns >= 50_000_000:
                if issue_boot_trust(self.path, self.policy) != self.trust:
                    raise ValueError()
                after = time.monotonic_ns()
                expires = min(now + 100_000_000, self.trust.valid_until_ns)
                if type(after) is not int or not now <= after < expires:
                    raise ValueError()
                self.checked_ns, self.last_ns, self.expires_ns = now, after, expires
            return self.expires_ns
        except (OSError, ValueError, TypeError, OverflowError):
            self.closed = True
            raise ValueError("clock_authority_rejected") from None


def initialize_boot_authority(path, policy, *, timestamp_floor):
    """Explicit first provisioning; publish complete state without replacing paths.

    The administrator supplies the anti-replay floor. No time sampling, packet
    trust, grant issuance or recovery/reset of existing state occurs here.
    """
    try:
        if type(policy) is not BootClockPolicy:
            raise ValueError("invalid_policy")
        trust = SigningTrust(policy.key, policy.link_id, timestamp_floor, 0, 1)
        path = Path(path).absolute()
        _private_parent(path)
        if path.parent.is_symlink():
            raise ValueError("invalid_private_parent")
        # Private same-UID ancestor namespace is trusted, as for replay storage.
        # Hard-link publication is atomic/no-replace; rename would overwrite.
        with tempfile.TemporaryDirectory(prefix=".aethron-provision-", dir=path.parent) as work:
            staged = Path(work) / "replay.db"
            provision_replay(staged, trust, system=policy.system_id, component=policy.component_id)
            provision_boot_authority(staged, policy)
            _identity(staged)
            os.link(staged, path, follow_symlinks=False)
            staged.unlink()
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
        # Never remove the destination on failure: it may belong to a competing
        # initializer, or be complete published state after a durability error.
        raise ValueError("initial_telemetry_provisioning_failed") from None
