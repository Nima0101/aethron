"""Explicit initial state must never overwrite or expose partial replay journals."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from aethron_edge.telemetry import boot_authority as api


class InitialProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "replay.db"
        self.policy = api.BootClockPolicy(
            bytes(range(32)),
            1,
            2,
            7,
            api.MAVLINK_EPOCH_NS,
            api.MAVLINK_EPOCH_NS + 100_000_000_000,
            10_000_000_000,
            1_000_000,
        )

    def initialize(self, floor=123):
        return api.initialize_boot_authority(self.path, self.policy, timestamp_floor=floor)

    def test_new_journal_is_bound_with_exact_operator_floor_and_no_issued_grant(self):
        self.initialize()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(
                db.execute("SELECT scope,timestamp FROM replay").fetchone(),
                (self.policy.scope, 123),
            )
            self.assertEqual(
                db.execute("SELECT policy,boot FROM boot_authority").fetchone(),
                (self.policy.digest, None),
            )
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.stat().st_nlink, 1)
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_existing_valid_state_or_dangling_link_is_never_overwritten(self):
        self.initialize()
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.initialize(0)
        self.assertEqual(self.path.read_bytes(), before)
        self.path.unlink()
        self.path.symlink_to(self.root / "missing")
        with self.assertRaises(ValueError):
            self.initialize()
        self.assertTrue(self.path.is_symlink())
        self.assertFalse((self.root / "missing").exists())

    def test_failure_before_publication_leaves_no_visible_partial_state(self):
        with patch.object(
            api, "provision_boot_authority", side_effect=ValueError("private failure")
        ):
            with self.assertRaisesRegex(ValueError, "^initial_telemetry_provisioning_failed$"):
                self.initialize()
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_post_publication_durability_failure_preserves_complete_state(self):
        with patch.object(api.os, "fsync", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(ValueError, "^initial_telemetry_provisioning_failed$"):
                self.initialize()
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT timestamp FROM replay").fetchone(), (123,))
            self.assertEqual(db.execute("SELECT boot FROM boot_authority").fetchone(), (None,))
        self.assertEqual(self.path.stat().st_nlink, 1)
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.initialize(0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_racing_destination_creation_is_preserved(self):
        import os

        link = os.link

        def competing(source, destination, **kwargs):
            self.path.write_bytes(b"competing state")
            return link(source, destination, **kwargs)

        with patch.object(api.os, "link", side_effect=competing):
            with self.assertRaises(ValueError):
                self.initialize()
        self.assertEqual(self.path.read_bytes(), b"competing state")
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_bad_floor_policy_and_private_directory_fail_before_publication(self):
        for floor in (True, -1, 1.0, 2**48):
            with self.assertRaises(ValueError):
                self.initialize(floor)
            self.assertFalse(self.path.exists())
        with self.assertRaises(ValueError):
            api.initialize_boot_authority(self.path, object(), timestamp_floor=0)
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            self.initialize()
        self.root.chmod(0o700)
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.path = alias / "replay.db"
        with self.assertRaises(ValueError):
            self.initialize()
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
