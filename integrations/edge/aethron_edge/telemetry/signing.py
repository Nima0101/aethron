"""Provisioned receive-only MAVLink signatures. SPDX-License-Identifier: GPL-3.0-only.

The local journal stores one replay counter, never observations. Its directory
must be private trusted host storage; filesystem rollback by that owner is not
detectable here. Provisioning and key distribution are deliberately out-of-band.
"""

import hashlib
import hmac
import os
import sqlite3
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path

from .mavlink import PassiveTelemetry

MAX_TIMESTAMP = (1 << 48) - 1
SIGNATURE_WINDOW = 6_000_000  # 60s, in MAVLink's 10 microsecond units.


@dataclass(frozen=True)
class SigningTrust:
    key: bytes = field(repr=False)
    link_id: int
    timestamp_floor: int
    issued_ns: int
    valid_until_ns: int
    boot_bound: bool = False

    def __post_init__(self):
        if (
            type(self.key) is not bytes
            or len(self.key) != 32
            or type(self.link_id) is not int
            or not 0 <= self.link_id <= 255
            or type(self.timestamp_floor) is not int
            or not 0 <= self.timestamp_floor < MAX_TIMESTAMP
            or type(self.issued_ns) is not int
            or type(self.valid_until_ns) is not int
            or not 0 <= self.issued_ns < self.valid_until_ns < 2**63
            or type(self.boot_bound) is not bool
        ):
            raise ValueError("invalid_signing_trust")


def _scope(trust, system, component):
    if any(type(x) is not int or not 1 <= x <= 255 for x in (system, component)):
        raise ValueError("invalid_sender")
    return hashlib.sha256(trust.key + bytes((system, component, trust.link_id))).hexdigest()


def _private_parent(path):
    # This journal currently requires POSIX ownership/mode enforcement.
    parent = path.parent.stat()
    if (
        not hasattr(os, "getuid")
        or not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.getuid()
        or parent.st_mode & 0o077
    ):
        raise ValueError("invalid_replay_store")


def _identity(path):
    _private_parent(path)
    item = path.lstat()
    if (
        not stat.S_ISREG(item.st_mode)
        or item.st_nlink != 1
        or item.st_uid != os.getuid()
        or item.st_mode & 0o777 != 0o600
        or item.st_size > 65536
    ):
        raise ValueError("invalid_replay_store")
    return item.st_dev, item.st_ino


def _connect(path):
    connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=0.02)
    try:
        connection.execute("PRAGMA synchronous=FULL")
    except BaseException:
        # Setup can fail before ownership is returned to the caller's finally.
        connection.close()
        raise
    return connection


def provision_replay(path: Path, trust: SigningTrust, *, system: int, component: int):
    """Explicit first provisioning; never overwrite/reset an existing counter.

    The caller supplies an authoritative timestamp floor and securely distributed
    key. Missing journals on normal startup are faults, not automatic provisioning.
    """
    path = Path(path).absolute()
    scope = _scope(trust, system, component)
    _private_parent(path)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    connection = _connect(path)
    try:
        connection.execute(
            "CREATE TABLE replay (id INTEGER PRIMARY KEY CHECK(id=1), "
            "scope TEXT NOT NULL, timestamp INTEGER NOT NULL)"
        )
        connection.execute("INSERT INTO replay VALUES (1, ?, ?)", (scope, trust.timestamp_floor))
        connection.commit()
    finally:
        connection.close()


class SignedTelemetry(PassiveTelemetry):
    """Signed-only observations with durable, key/stream-bound replay rejection.

    Authentication proves shared-key possession, not physical measurement truth,
    sensor-clock synchronization, individual device identity or field qualification.
    """

    _signature_bytes = 13

    def __init__(
        self, system, component, *, trust: SigningTrust, replay_path: Path, clock=time.monotonic_ns
    ):
        super().__init__(system, component, clock=clock)
        if type(trust) is not SigningTrust:
            raise ValueError("invalid_signing_trust")
        self._trust = trust
        self._path = Path(replay_path).absolute()
        self._scope = _scope(trust, system, component)
        self._boot_bound = trust.boot_bound
        try:
            self._file_identity = _identity(self._path)
            connection = _connect(self._path)
            try:
                self._read_counter(connection)
            finally:
                connection.close()
        except (OSError, sqlite3.Error, ValueError):
            raise ValueError("invalid_replay_store") from None

    def _read_counter(self, connection):
        if (
            connection.execute("SELECT 1 FROM sqlite_master WHERE name='boot_authority'").fetchone()
            is not None
        ):
            self._boot_bound = True
        if self._boot_bound:
            authority = connection.execute(
                "SELECT id, issued, expires, floor, revoked FROM boot_authority"
            ).fetchmany(2)
            trust = self._trust
            if authority != [(1, trust.issued_ns, trust.valid_until_ns, trust.timestamp_floor, 0)]:
                raise ValueError("invalid_boot_binding")
        rows = connection.execute("SELECT id, scope, timestamp FROM replay").fetchmany(2)
        if (
            len(rows) != 1
            or rows[0][0] != 1
            or rows[0][1] != self._scope
            or type(rows[0][2]) is not int
            or not 0 <= rows[0][2] <= MAX_TIMESTAMP
        ):
            raise ValueError("invalid_replay_store")
        return rows[0][2]

    def _authority_valid(self, now):
        if not self._trust.issued_ns <= now < self._trust.valid_until_ns:
            self._withdraw("signing_authority_expired", latch=True)
            return False
        return True

    def _decode_packet(self, packet, now):
        trust = self._trust
        timestamp = int.from_bytes(packet[-12:-6], "little")
        local_timestamp = trust.timestamp_floor + (now - trust.issued_ns) // 10_000
        if (
            packet[-13] != trust.link_id
            or timestamp <= trust.timestamp_floor
            or abs(timestamp - local_timestamp) > SIGNATURE_WINDOW
            or local_timestamp > MAX_TIMESTAMP
        ):
            self._withdraw("signature_time_or_link")
            return None
        expected = hashlib.sha256(trust.key + packet[:-6]).digest()[:6]
        if not hmac.compare_digest(expected, packet[-6:]):
            self._withdraw("invalid_signature")
            return None
        # pymavlink 2.4.50 mutates stream counters before checking the signature.
        # Isolate that state per decode; only our post-validation transaction
        # commits replay state. No unsigned callback or outbound writer exists.
        decoder = self._common.MAVLink(None)
        decoder.signing.secret_key = trust.key
        decoder.signing.timestamp = local_timestamp
        message = decoder.decode(bytearray(packet))
        if not message.get_signed():
            self._withdraw("invalid_signature")
            return None
        return message

    def _commit_packet(self, packet):
        timestamp = int.from_bytes(packet[-12:-6], "little")
        try:
            if _identity(self._path) != self._file_identity:
                raise ValueError("invalid_replay_store")
            connection = _connect(self._path)
            try:
                connection.execute("BEGIN IMMEDIATE")
                if timestamp <= self._read_counter(connection):
                    self._withdraw("signature_replay")
                    return False
                connection.execute("UPDATE replay SET timestamp=? WHERE id=1", (timestamp,))
                connection.commit()  # Persist before publishing an observation.
                if _identity(self._path) != self._file_identity:
                    raise ValueError("invalid_replay_store")
            finally:
                connection.close()
        except (OSError, sqlite3.Error, ValueError):
            self._withdraw("replay_store_failed", latch=True)
            return False
        return True

    def close(self):
        super().close()
        self._trust = None  # Release references; Python does not guarantee zeroization.
