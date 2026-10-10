"""Bounded synthetic rollout records; no installers or transport."""

import importlib.util
import itertools
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch


class FleetRolloutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "rollout.db"

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec("aethron_edge.runtime.fleet_rollout"))
        from aethron_edge.runtime import fleet_rollout

        return fleet_rollout

    def create(self, **changes):
        options = {
            "policy_sha256": "a" * 64,
            "artifact_sha256": "b" * 64,
            "version": 3,
            "slot_count": 5,
            "batch_size": 2,
            "not_before_unix_s": 1000,
            "expires_unix_s": 2000,
            "now_unix_s": 1000,
        }
        options.update(changes)
        return self.module().RolloutJournal.initialize(self.path, **options)

    def reject(self, fn, **kwargs):
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_rollout$"):
            fn(**kwargs)

    def finish(self, journal, slot, *, outcome="succeeded", digest="b" * 64, now=1002):
        return journal.record(
            slot=slot,
            outcome=outcome,
            artifact_sha256=digest,
            policy_sha256="a" * 64,
            expected_revision=journal.snapshot().revision,
            now_unix_s=now,
        )

    def test_bounded_waves_reopen_and_complete_without_repeating_slots(self):
        journal = self.create()
        self.assertEqual(journal.snapshot().states, ("pending",) * 5)
        self.assertEqual(journal.claim(expected_revision=0, now_unix_s=1001), (0, 1))
        journal = self.module().RolloutJournal(self.path)
        self.reject(journal.claim, expected_revision=1, now_unix_s=1002)
        self.finish(journal, 0)
        self.finish(journal, 1)
        self.assertEqual(journal.claim(expected_revision=3, now_unix_s=1003), (2, 3))
        self.finish(journal, 2, now=1004)
        self.finish(journal, 3, now=1004)
        self.assertEqual(journal.claim(expected_revision=6, now_unix_s=1005), (4,))
        self.finish(journal, 4, now=1006)
        self.assertEqual(journal.snapshot().states, ("succeeded",) * 5)
        self.reject(journal.claim, expected_revision=8, now_unix_s=1007)

    def test_failure_remains_sticky_across_reopen_and_other_receipts(self):
        journal = self.create()
        journal.claim(expected_revision=0, now_unix_s=1001)
        self.finish(journal, 0, outcome="failed")
        self.finish(journal, 1)
        journal = self.module().RolloutJournal(self.path)
        self.reject(journal.claim, expected_revision=3, now_unix_s=1003)
        self.reject(
            journal.record,
            slot=0,
            outcome="succeeded",
            artifact_sha256="b" * 64,
            policy_sha256="a" * 64,
            expected_revision=3,
            now_unix_s=1003,
        )
        self.assertEqual(
            journal.snapshot().states, ("failed", "succeeded", "pending", "pending", "pending")
        )

    def test_stale_revision_cannot_claim_or_rewrite_progress(self):
        journal = self.create()
        other = self.module().RolloutJournal(self.path)
        journal.claim(expected_revision=0, now_unix_s=1001)
        self.reject(other.claim, expected_revision=0, now_unix_s=1002)
        self.reject(
            other.record,
            slot=0,
            outcome="succeeded",
            artifact_sha256="b" * 64,
            policy_sha256="a" * 64,
            expected_revision=0,
            now_unix_s=1002,
        )
        self.assertEqual(journal.snapshot().revision, 1)

    def test_mismatched_content_and_invalid_receipts_never_advance(self):
        journal = self.create()
        journal.claim(expected_revision=0, now_unix_s=1001)
        base = {
            "slot": 0,
            "outcome": "succeeded",
            "artifact_sha256": "b" * 64,
            "policy_sha256": "a" * 64,
            "expected_revision": 1,
            "now_unix_s": 1002,
        }
        for change in (
            {"artifact_sha256": "c" * 64},
            {"policy_sha256": "c" * 64},
            {"slot": True},
            {"slot": 2},
            {"slot": 5},
            {"outcome": "healthy"},
            {"outcome": []},
            {"expected_revision": True},
        ):
            with self.subTest(change=change):
                self.reject(journal.record, **(base | change))
                self.assertEqual(journal.snapshot().revision, 1)

    def test_invalid_clock_expiry_and_rollback_preserve_state(self):
        journal = self.create()
        for now in (999, 2000, True, None, 1000.0):
            self.reject(journal.claim, expected_revision=0, now_unix_s=now)
        journal.claim(expected_revision=0, now_unix_s=1002)
        self.reject(
            journal.record,
            slot=0,
            outcome="failed",
            artifact_sha256="b" * 64,
            policy_sha256="a" * 64,
            expected_revision=1,
            now_unix_s=1001,
        )
        self.assertEqual(journal.snapshot().revision, 1)

    def test_initialization_is_exclusive_and_validates_before_creating(self):
        for change in (
            {"slot_count": 1025},
            {"batch_size": 0},
            {"batch_size": 6},
            {"version": True},
            {"policy_sha256": "A" * 64},
            {"artifact_sha256": "x"},
            {"expires_unix_s": 87401},
            {"now_unix_s": 2000},
        ):
            self.reject(self.create, **change)
            self.assertFalse(self.path.exists())
        journal = self.create()
        before = journal.snapshot()
        self.reject(self.create)
        self.assertEqual(journal.snapshot(), before)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_missing_corrupt_link_and_foreign_schema_do_not_reset(self):
        journal = self.create()
        self.path.unlink()
        self.reject(journal.snapshot)
        self.assertFalse(self.path.exists())
        self.path.write_bytes(b"corrupt")
        self.reject(journal.snapshot)
        self.path.unlink()
        target = self.path.with_name("other")
        target.write_text("private")
        self.path.symlink_to(target)
        self.reject(journal.snapshot)
        self.assertEqual(target.read_text(), "private")
        self.path.unlink()
        journal = self.create()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TABLE surprise (x)")
        self.reject(journal.snapshot)

    def test_commit_failure_returns_no_claim_and_persists_no_progress(self):
        journal = self.create()
        original = sqlite3.connect

        class FailingCommit(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("injected")
                return super().execute(sql, parameters)

        def connect(*args, **kwargs):
            return original(*args, factory=FailingCommit, **kwargs)

        with patch("aethron_edge.runtime.fleet_rollout.sqlite3.connect", connect):
            self.reject(journal.claim, expected_revision=0, now_unix_s=1001)
        self.assertEqual(journal.snapshot().revision, 0)
        self.assertEqual(journal.snapshot().states, ("pending",) * 5)

    def test_every_commit_uses_verified_delete_extra_profile(self):
        original = sqlite3.connect
        observed = []

        class ObservedCommit(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    observed.append(
                        (
                            super().execute("PRAGMA journal_mode").fetchone()[0],
                            super().execute("PRAGMA synchronous").fetchone()[0],
                        )
                    )
                return super().execute(sql, parameters)

        def connect(*args, **kwargs):
            return original(*args, factory=ObservedCommit, **kwargs)

        with patch("aethron_edge.runtime.fleet_rollout.sqlite3.connect", connect):
            journal = self.create()
            journal.claim(expected_revision=0, now_unix_s=1001)
            self.finish(journal, 0, outcome="failed")
        self.assertEqual(observed, [("delete", 3)] * 3)

    def test_unavailable_durability_profile_rejects_before_mutation(self):
        original = sqlite3.connect
        for setting in ("synchronous", "journal_mode"):
            with self.subTest(setting=setting):
                self.path = self.path.with_name(setting + ".db")
                journal = self.create()
                before = journal.snapshot()

                class WeakerProfile(sqlite3.Connection):
                    def execute(self, sql, parameters=(), *, selected=setting):
                        if sql.startswith("PRAGMA " + selected + "="):
                            sql = (
                                "PRAGMA synchronous=OFF"
                                if selected == "synchronous"
                                else "PRAGMA journal_mode=MEMORY"
                            )
                        return super().execute(sql, parameters)

                def connect(*args, **kwargs):
                    return original(*args, factory=WeakerProfile, **kwargs)

                with patch("aethron_edge.runtime.fleet_rollout.sqlite3.connect", connect):
                    self.reject(journal.claim, expected_revision=0, now_unix_s=1001)
                self.assertEqual(journal.snapshot(), before)

    def test_process_exit_at_commit_keeps_atomic_reservations_and_failure(self):
        program = """
import os, sqlite3, sys
from pathlib import Path
from unittest.mock import patch
from aethron_edge.runtime.fleet_rollout import RolloutJournal
original = sqlite3.connect
mode, operation = sys.argv[2:]
class ExitAtCommit(sqlite3.Connection):
    def execute(self, sql, parameters=()):
        if sql == "COMMIT" and mode == "before":
            os._exit(91)
        result = super().execute(sql, parameters)
        if sql == "COMMIT" and mode == "after":
            os._exit(92)
        return result
def connect(*args, **kwargs):
    return original(*args, factory=ExitAtCommit, **kwargs)
journal = RolloutJournal(Path(sys.argv[1]))
with patch("aethron_edge.runtime.fleet_rollout.sqlite3.connect", connect):
    if operation == "claim":
        journal.claim(expected_revision=0, now_unix_s=1001)
    else:
        journal.record(slot=0, outcome="failed", policy_sha256="a"*64,
                       artifact_sha256="b"*64, expected_revision=1, now_unix_s=1002)
raise RuntimeError("commit injection was not reached")
"""
        for operation in ("claim", "record"):
            for mode in ("before", "after"):
                with self.subTest(operation=operation, mode=mode):
                    self.path = self.path.with_name(operation + "-" + mode + ".db")
                    journal = self.create()
                    if operation == "record":
                        journal.claim(expected_revision=0, now_unix_s=1001)
                    before = journal.snapshot()
                    child = subprocess.run(
                        [sys.executable, "-c", program, str(self.path), mode, operation],
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                    self.assertEqual(child.returncode, 91 if mode == "before" else 92, child.stderr)
                    recovered = self.module().RolloutJournal(self.path)
                    if mode == "before":
                        self.assertEqual(recovered.snapshot(), before)
                    else:
                        snapshot = recovered.snapshot()
                        self.assertEqual(snapshot.revision, before.revision + 1)
                        self.assertEqual(
                            snapshot.states,
                            ("running" if operation == "claim" else "failed", "running")
                            + ("pending",) * 3,
                        )
                        self.reject(
                            recovered.claim, expected_revision=snapshot.revision, now_unix_s=1003
                        )

    def test_maximum_capacity_and_lock_contention_are_bounded(self):
        journal = self.create(slot_count=1024, batch_size=32)
        with closing(sqlite3.connect(self.path)) as writer, writer:
            writer.execute("BEGIN IMMEDIATE")
            self.reject(journal.claim, expected_revision=0, now_unix_s=1001)
        self.assertEqual(journal.claim(expected_revision=0, now_unix_s=1001), tuple(range(32)))
        self.assertLess(self.path.stat().st_size, 1024 * 1024)

    def test_small_state_space_matches_independent_transition_exploration(self):
        self.create(slot_count=4, batch_size=1)
        with closing(sqlite3.connect(self.path)) as db:
            template = json.loads(db.execute("SELECT payload FROM rollout").fetchone()[0])
        module = self.module()
        for batch in range(1, 5):
            # Enumerate executable transitions, not the validator's count formula.
            initial = (("pending",) * 4, 0)
            reachable = {initial}
            todo = [initial]
            while todo:
                states, revision = todo.pop()
                successors = []
                if "running" not in states and "failed" not in states and "pending" in states:
                    updated = list(states)
                    remaining = batch
                    for slot, state in enumerate(states):
                        if state == "pending" and remaining:
                            updated[slot] = "running"
                            remaining -= 1
                    successors.append(tuple(updated))
                for slot, state in enumerate(states):
                    if state == "running":
                        for outcome in ("succeeded", "failed"):
                            updated = list(states)
                            updated[slot] = outcome
                            successors.append(tuple(updated))
                for states in successors:
                    candidate = (states, revision + 1)
                    if candidate not in reachable:
                        reachable.add(candidate)
                        todo.append(candidate)
            for states in itertools.product(
                ("pending", "running", "succeeded", "failed"), repeat=4
            ):
                for revision in range(9):
                    value = template | {
                        "batch_size": batch,
                        "states": list(states),
                        "revision": revision,
                    }
                    try:
                        module._validate(value)
                        admitted = True
                    except ValueError:
                        admitted = False
                    self.assertEqual(
                        admitted, (states, revision) in reachable, (batch, states, revision)
                    )

    def test_deeply_nested_corrupt_payload_uses_fixed_error(self):
        journal = self.create()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE rollout SET payload=?", ("[" * 1200 + "]" * 1200,))
        self.reject(journal.snapshot)


if __name__ == "__main__":
    unittest.main()
