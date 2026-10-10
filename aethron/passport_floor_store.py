"""Local policy floors, under caller-controlled storage and trusted clock/pin inputs.

Not filesystem rollback detection, enrollment, encryption or execution authority.
"""

import os
import sqlite3
import stat
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .passports import _HEX, _integer, _token, validate_pinned_policy

_APPLICATION_ID = 0x41544631
_SCHEMA = (
    "CREATE TABLE policy_floor (id INTEGER PRIMARY KEY CHECK(id=1), "
    "scope TEXT NOT NULL, revision INTEGER NOT NULL, time_s INTEGER NOT NULL, "
    "policy_sha256 TEXT NOT NULL)"
)


class FloorStoreError(ValueError):
    """Fixed failure reason; callers must not substitute zero/default floors."""


@dataclass(frozen=True)
class PolicyFloor:
    scope: str
    policy_revision: int
    minimum_time_s: int
    policy_sha256: str
    execution_authority: bool = field(default=False, init=False)
    motion_authority: bool = field(default=False, init=False)
    evidence_verified: bool = field(default=False, init=False)


def _configuration(path, scope):
    try:
        _token(scope)
        if type(path) is not str or not 1 <= len(path) <= 4096 or "\x00" in path:
            raise ValueError
        path.encode("utf-8")
        result = Path(path)
        if not result.is_absolute():
            raise ValueError
        return result
    except (ValueError, TypeError):
        raise FloorStoreError("invalid_configuration") from None


def _time(value):
    try:
        _integer(value)
    except ValueError:
        raise FloorStoreError("invalid_time") from None


class PolicyFloorStore:
    """One scope per protected local file; each operation opens its own transaction."""

    def __init__(self, path: str, *, scope: str):
        self._path = _configuration(path, scope)
        self._scope = scope
        self.read()  # No implicit initialization, repair or recovery to default floors.

    @classmethod
    def create(
        cls,
        path: str,
        *,
        scope: str,
        policy: bytes,
        expected_policy_sha256: str,
        now_s: int,
        minimum_time_s: int,
        minimum_policy_revision: int,
    ):
        target = _configuration(path, scope)
        admitted = validate_pinned_policy(
            policy,
            expected_policy_sha256=expected_policy_sha256,
            now_s=now_s,
            minimum_time_s=minimum_time_s,
            minimum_policy_revision=minimum_policy_revision,
        )
        if admitted.status != "validated":
            raise FloorStoreError("policy_rejected")
        # Leave any partial file after a failed initialization for explicit recovery.
        try:
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except OSError:
            raise FloorStoreError("store_unavailable") from None
        instance = cls.__new__(cls)
        instance._path, instance._scope = target, scope
        with instance._transaction(initializing=True) as db:
            db.execute(_SCHEMA)
            db.execute("PRAGMA application_id=1096042033")
            db.execute("PRAGMA user_version=1")
            db.execute(
                "INSERT INTO policy_floor VALUES (1, ?, ?, ?, ?)",
                (scope, admitted.policy_revision, now_s, admitted.policy_sha256),
            )
        return instance

    @contextmanager
    def _transaction(self, *, initializing=False):
        db = None
        try:
            info = self._path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
                raise FloorStoreError("invalid_store")
            db = sqlite3.connect(
                self._path.as_uri() + "?mode=rw",
                uri=True,
                timeout=0,
                isolation_level=None,
                cached_statements=0,
            )
            db.execute("PRAGMA trusted_schema=OFF")
            if db.execute("PRAGMA trusted_schema").fetchone() != (0,):
                raise FloorStoreError("unsupported_storage")
            if initializing:
                db.execute("PRAGMA page_size=4096")
                db.execute("PRAGMA journal_mode=DELETE")
            if db.execute("PRAGMA journal_mode").fetchone() != ("delete",):
                raise FloorStoreError("invalid_store")
            db.execute("PRAGMA synchronous=EXTRA")
            if db.execute("PRAGMA synchronous").fetchone() != (3,):
                raise FloorStoreError("unsupported_storage")
            db.execute("PRAGMA cache_size=-64")
            # SQLite cannot lower this below an existing file's page count.
            if db.execute("PRAGMA max_page_count=16").fetchone() != (16,):
                raise FloorStoreError("invalid_store")
            db.execute("BEGIN IMMEDIATE")
            if not initializing:
                self._row(db)
            yield db
            db.execute("COMMIT")
        except (sqlite3.Error, OSError):
            raise FloorStoreError("store_unavailable") from None
        finally:
            if db is not None:
                # Closing an uncommitted connection rolls back, including interruptions.
                db.close()

    def _row(self, db):
        if (
            db.execute("PRAGMA application_id").fetchone() != (_APPLICATION_ID,)
            or db.execute("PRAGMA user_version").fetchone() != (1,)
            or db.execute("SELECT type, name, sql FROM sqlite_master").fetchmany(2)
            != [("table", "policy_floor", _SCHEMA)]
        ):
            raise FloorStoreError("invalid_store")
        rows = db.execute(
            "SELECT id, scope, revision, time_s, policy_sha256 FROM policy_floor"
        ).fetchmany(2)
        try:
            if len(rows) != 1 or rows[0][0] != 1 or rows[0][1] != self._scope:
                raise ValueError
            _, scope, revision, time_s, digest = rows[0]
            _token(scope)
            _integer(revision, 1)
            _integer(time_s)
            _token(digest, _HEX)
        except (ValueError, TypeError):
            raise FloorStoreError("invalid_store") from None
        return PolicyFloor(scope, revision, time_s, digest)

    def read(self) -> PolicyFloor:
        with self._transaction() as db:
            return self._row(db)

    def observe_time(self, *, now_s: int) -> PolicyFloor:
        """Record an independently trusted clock observation, even after policy expiry."""
        _time(now_s)
        with self._transaction() as db:
            previous = self._row(db)
            if now_s < previous.minimum_time_s:
                raise FloorStoreError("time_rollback")
            db.execute("UPDATE policy_floor SET time_s=? WHERE id=1", (now_s,))
            return self._row(db)

    def accept_policy(
        self,
        policy: bytes,
        *,
        expected_policy_sha256: str,
        now_s: int,
    ) -> PolicyFloor:
        """Validate an externally pinned policy under the current persisted floors."""
        with self._transaction() as db:
            previous = self._row(db)
            admitted = validate_pinned_policy(
                policy,
                expected_policy_sha256=expected_policy_sha256,
                now_s=now_s,
                minimum_time_s=previous.minimum_time_s,
                minimum_policy_revision=previous.policy_revision,
            )
            if admitted.status != "validated":
                raise FloorStoreError("policy_rejected")
            if (
                admitted.policy_revision == previous.policy_revision
                and admitted.policy_sha256 != previous.policy_sha256
            ):
                raise FloorStoreError("policy_equivocation")
            db.execute(
                "UPDATE policy_floor SET revision=?, time_s=?, policy_sha256=? WHERE id=1",
                (admitted.policy_revision, now_s, admitted.policy_sha256),
            )
            return self._row(db)
