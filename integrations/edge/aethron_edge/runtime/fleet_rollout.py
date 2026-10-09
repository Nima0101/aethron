"""Bounded local rollout bookkeeping. No authentication, transport or installer."""

import json
import os
import re
import sqlite3
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ..config import strict_json

_SCHEMA = (
    "CREATE TABLE rollout (singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL)"
)
_FIELDS = frozenset(
    (
        "schema_version",
        "policy_sha256",
        "artifact_sha256",
        "version",
        "slot_count",
        "batch_size",
        "not_before_unix_s",
        "expires_unix_s",
        "last_time_s",
        "revision",
        "states",
    )
)


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _validate(value):
    if type(value) is not dict or value.keys() != _FIELDS:
        raise ValueError()
    for name in ("policy_sha256", "artifact_sha256"):
        if type(value[name]) is not str or not re.fullmatch("[0-9a-f]{64}", value[name]):
            raise ValueError()
    if (
        not _integer(value["schema_version"], 1, 1)
        or not _integer(value["version"], 1, 2**31 - 1)
        or not _integer(value["slot_count"], 1, 1024)
        or not _integer(value["batch_size"], 1, min(32, value["slot_count"]))
        or not _integer(value["not_before_unix_s"], 0, 2**53 - 1)
        or not _integer(value["expires_unix_s"], 0, 2**53 - 1)
        or not 1 <= value["expires_unix_s"] - value["not_before_unix_s"] <= 86400
        or not _integer(
            value["last_time_s"], value["not_before_unix_s"], value["expires_unix_s"] - 1
        )
        or not _integer(value["revision"], 0, 2048)
    ):
        raise ValueError()
    states = value["states"]
    if (
        type(states) is not list
        or len(states) != value["slot_count"]
        or any(
            type(s) is not str or s not in ("pending", "running", "succeeded", "failed")
            for s in states
        )
    ):
        raise ValueError()
    started = sum(s != "pending" for s in states)
    completed = sum(s in ("succeeded", "failed") for s in states)
    batch = value["batch_size"]
    waves = (started + batch - 1) // batch
    if (
        states[started:] != ["pending"] * (len(states) - started)
        or (started != len(states) and started % batch != 0)
        or any(s != "succeeded" for s in states[: max(0, (waves - 1) * batch)])
        or states.count("running") > batch
        or value["revision"] != waves + completed
    ):
        raise ValueError()
    return value


@dataclass(frozen=True)
class RolloutSnapshot:
    policy_sha256: str
    artifact_sha256: str
    version: int
    slot_count: int
    batch_size: int
    not_before_unix_s: int
    expires_unix_s: int
    last_time_s: int
    revision: int
    states: tuple[str, ...]


class RolloutJournal:
    """One immutable plan in a protected local directory; caller authenticates it."""

    def __init__(self, path: Path):
        try:
            self.path = Path(path).absolute()
        except (OSError, TypeError, ValueError):
            raise ValueError("invalid_fleet_rollout") from None

    @classmethod
    def initialize(
        cls,
        path: Path,
        *,
        policy_sha256: str,
        artifact_sha256: str,
        version: int,
        slot_count: int,
        batch_size: int,
        not_before_unix_s: int,
        expires_unix_s: int,
        now_unix_s: int,
    ):
        try:
            if not _integer(slot_count, 1, 1024):
                raise ValueError()
            value = _validate(
                {
                    "schema_version": 1,
                    "policy_sha256": policy_sha256,
                    "artifact_sha256": artifact_sha256,
                    "version": version,
                    "slot_count": slot_count,
                    "batch_size": batch_size,
                    "not_before_unix_s": not_before_unix_s,
                    "expires_unix_s": expires_unix_s,
                    "last_time_s": now_unix_s,
                    "revision": 0,
                    "states": ["pending"] * slot_count,
                }
            )
            journal = cls(path)
            fd = os.open(journal.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            with journal._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(_SCHEMA)
                db.execute("INSERT INTO rollout VALUES (1, ?)", (json.dumps(value),))
                db.execute("COMMIT")
            return journal
        except (OSError, TypeError, ValueError, RecursionError, sqlite3.Error):
            raise ValueError("invalid_fleet_rollout") from None

    @contextmanager
    def _connection(self):
        db = None
        try:
            metadata = self.path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1024 * 1024:
                raise ValueError()
            db = sqlite3.connect(
                self.path.as_uri() + "?mode=rw", uri=True, timeout=0.1, isolation_level=None
            )
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 32768)
            db.execute("PRAGMA trusted_schema=OFF")
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA max_page_count=256")
            yield db
        except (OSError, TypeError, ValueError, RecursionError, sqlite3.Error):
            raise ValueError("invalid_fleet_rollout") from None
        finally:
            if db is not None:
                db.close()

    @staticmethod
    def _read(db):
        schema = db.execute("SELECT type, name, sql FROM sqlite_schema").fetchmany(2)
        if schema != [("table", "rollout", _SCHEMA)]:
            raise ValueError()
        rows = db.execute("SELECT singleton, payload FROM rollout").fetchmany(2)
        if len(rows) != 1 or rows[0][0] != 1 or type(rows[0][1]) is not str:
            raise ValueError()
        return _validate(strict_json(rows[0][1], 16384))

    def snapshot(self) -> RolloutSnapshot:
        with self._connection() as db:
            db.execute("BEGIN")
            value = self._read(db)
        return RolloutSnapshot(
            **{
                k: tuple(v) if k == "states" else v
                for k, v in value.items()
                if k != "schema_version"
            }
        )

    def _mutate(self, expected_revision, now_unix_s, operation):
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            value = self._read(db)
            if (
                not _integer(expected_revision, 0, 2048)
                or expected_revision != value["revision"]
                or not _integer(now_unix_s, value["last_time_s"], value["expires_unix_s"] - 1)
            ):
                raise ValueError()
            result = operation(value)
            value["revision"] += 1
            value["last_time_s"] = now_unix_s
            _validate(value)
            db.execute("UPDATE rollout SET payload=? WHERE singleton=1", (json.dumps(value),))
            db.execute("COMMIT")
        return result

    def claim(self, *, expected_revision: int, now_unix_s: int) -> tuple[int, ...]:
        """Commit a wave reservation; returned slots confer no execution authority."""

        def operation(value):
            states = value["states"]
            if "failed" in states or "running" in states:
                raise ValueError()
            slots = tuple(i for i, state in enumerate(states) if state == "pending")[
                : value["batch_size"]
            ]
            if not slots:
                raise ValueError()
            for slot in slots:
                states[slot] = "running"
            return slots

        return self._mutate(expected_revision, now_unix_s, operation)

    def record(
        self,
        *,
        slot: int,
        outcome: str,
        artifact_sha256: str,
        policy_sha256: str,
        expected_revision: int,
        now_unix_s: int,
    ):
        """Record a trusted caller's software result; never erase terminal failure."""

        def operation(value):
            if (
                not _integer(slot, 0, value["slot_count"] - 1)
                or type(outcome) is not str
                or outcome not in ("succeeded", "failed")
                or type(artifact_sha256) is not str
                or artifact_sha256 != value["artifact_sha256"]
                or type(policy_sha256) is not str
                or policy_sha256 != value["policy_sha256"]
                or value["states"][slot] != "running"
            ):
                raise ValueError()
            value["states"][slot] = outcome

        self._mutate(expected_revision, now_unix_s, operation)
