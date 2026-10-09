"""Bounded synthetic rollout records; no installers or transport."""

import importlib.util
import sqlite3
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

    def test_maximum_capacity_and_lock_contention_are_bounded(self):
        journal = self.create(slot_count=1024, batch_size=32)
        with closing(sqlite3.connect(self.path)) as writer, writer:
            writer.execute("BEGIN IMMEDIATE")
            self.reject(journal.claim, expected_revision=0, now_unix_s=1001)
        self.assertEqual(journal.claim(expected_revision=0, now_unix_s=1001), tuple(range(32)))
        self.assertLess(self.path.stat().st_size, 1024 * 1024)

    def test_deeply_nested_corrupt_payload_uses_fixed_error(self):
        journal = self.create()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE rollout SET payload=?", ("[" * 1200 + "]" * 1200,))
        self.reject(journal.snapshot)


if __name__ == "__main__":
    unittest.main()
