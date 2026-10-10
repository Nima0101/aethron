"""Committed local version/time floors; no policy authentication or deployment."""

import os
import sqlite3
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = (
    "CREATE TABLE fleet_floor ("
    "singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
    "schema_version INTEGER NOT NULL CHECK(schema_version=1), "
    "minimum_version INTEGER NOT NULL, minimum_time_s INTEGER NOT NULL)"
)


@dataclass(frozen=True)
class FleetFloors:
    minimum_version: int
    minimum_time_s: int


def _values(version, time_s):
    if (
        type(version) is not int
        or not 1 <= version <= 2**31 - 1
        or type(time_s) is not int
        or not 0 <= time_s <= 2**53 - 1
    ):
        raise ValueError("invalid_fleet_floor")
    return FleetFloors(version, time_s)


class FleetFloorStore:
    """Use only inside an administrator-controlled local directory, never NFS."""

    def __init__(self, path: Path):
        try:
            self.path = Path(path).absolute()
        except (OSError, ValueError, TypeError):
            raise ValueError("invalid_fleet_floor") from None

    @classmethod
    def initialize(cls, path: Path, *, minimum_version: int, minimum_time_s: int):
        _values(minimum_version, minimum_time_s)
        store = cls(path)
        try:
            fd = os.open(store.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            # An interrupted creation stays unusable; never replace/reset it.
            with store._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(_SCHEMA)
                connection.execute(
                    "INSERT INTO fleet_floor VALUES (1, 1, ?, ?)",
                    (minimum_version, minimum_time_s),
                )
                connection.execute("COMMIT")
        except (OSError, sqlite3.Error):
            raise ValueError("invalid_fleet_floor") from None
        return store

    @contextmanager
    def _connection(self):
        connection = None
        try:
            metadata = self.path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1024 * 1024:
                raise ValueError()
            # mode=rw rejects disappearance; ordinary connect would create a DB.
            connection = sqlite3.connect(
                self.path.as_uri() + "?mode=rw", uri=True, timeout=0.1, isolation_level=None
            )
            connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 4096)
            connection.execute("PRAGMA trusted_schema=OFF")
            if connection.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
                raise ValueError()
            # DELETE-mode durability also requires syncing the journal directory
            # after unlink. FULL alone can lose the last acknowledged transaction.
            connection.execute("PRAGMA synchronous=EXTRA")
            if connection.execute("PRAGMA synchronous").fetchone() != (3,):
                raise ValueError()
            connection.execute("PRAGMA max_page_count=256")
            yield connection
        except (OSError, sqlite3.Error, ValueError):
            raise ValueError("invalid_fleet_floor") from None
        finally:
            if connection is not None:
                # Closing an uncommitted connection rolls the transaction back.
                connection.close()

    @staticmethod
    def _read(connection):
        schema = connection.execute("SELECT type, name, sql FROM sqlite_schema").fetchmany(2)
        if schema != [("table", "fleet_floor", _SCHEMA)]:
            raise ValueError("invalid_fleet_floor")
        rows = connection.execute("SELECT * FROM fleet_floor").fetchmany(2)
        if len(rows) != 1 or rows[0][:2] != (1, 1):
            raise ValueError("invalid_fleet_floor")
        return _values(rows[0][2], rows[0][3])

    def read(self) -> FleetFloors:
        with self._connection() as connection:
            return self._read(connection)

    def advance(self, *, minimum_version: int, minimum_time_s: int) -> FleetFloors:
        with self.guarded_advance(
            minimum_version=minimum_version, minimum_time_s=minimum_time_s
        ) as updated:
            pass
        return updated

    @contextmanager
    def guarded_advance(self, *, minimum_version: int, minimum_time_s: int):
        """Hold the writer lock around local bookkeeping, committing on exit.

        The yielded floors are provisional. Never perform external execution
        inside this context or report success before it exits successfully.
        """
        updated = _values(minimum_version, minimum_time_s)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._read(connection)
            if minimum_version < current.minimum_version or minimum_time_s < current.minimum_time_s:
                raise ValueError("invalid_fleet_floor")
            connection.execute(
                "UPDATE fleet_floor SET minimum_version=?, minimum_time_s=? WHERE singleton=1",
                (minimum_version, minimum_time_s),
            )
            yield updated
            connection.execute("COMMIT")
