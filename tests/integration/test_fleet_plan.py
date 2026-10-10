"""Bind real signed private snapshots to local rollout journals."""

import hashlib
import importlib.util
import json
import unittest
from unittest.mock import patch

import test_fleet_policy as fixtures
from aethron_edge.runtime.fleet_floors import FleetFloors, FleetFloorStore


class FleetPlanTests(unittest.TestCase):
    run_crypto = fixtures.FleetPolicyTests.run_crypto
    sign = fixtures.FleetPolicyTests.sign

    def setUp(self):
        fixtures.FleetPolicyTests.setUp(self)
        self.store = FleetFloorStore.initialize(
            self.root / "floors.db", minimum_version=1, minimum_time_s=900
        )
        self.journal = self.root / "journal.db"
        self.sign()
        self.artifact = b"synthetic inert software payload"
        (self.bundle / "fleet-artifact.bin").write_bytes(self.artifact)
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        manifest["files"]["fleet-artifact.bin"] = hashlib.sha256(self.artifact).hexdigest()
        (self.bundle / "manifest.json").write_text(json.dumps(manifest))
        self.run_crypto(
            "pkeyutl",
            "-sign",
            "-rawin",
            "-inkey",
            str(self.private),
            "-in",
            str(self.bundle / "manifest.json"),
            "-out",
            str(self.bundle / "manifest.sig"),
        )

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec("aethron_edge.runtime.fleet_plan"))
        from aethron_edge.runtime import fleet_plan

        return fleet_plan

    def create(self, times=(1000, 1001, 1002)):
        samples = iter(times)
        return self.module().create_rollout_plan(
            self.bundle,
            self.public,
            journal_path=self.journal,
            floor_store=self.store,
            clock=lambda: next(samples),
        )

    def reject(self, times=(1000, 1001, 1002)):
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_plan$"):
            self.create(times)

    def test_signed_snapshot_binds_exact_policy_artifact_and_bounds(self):
        journal = self.create()
        value = journal.snapshot()
        self.assertEqual(
            value.policy_sha256,
            hashlib.sha256((self.bundle / "fleet-policy.json").read_bytes()).hexdigest(),
        )
        self.assertEqual(value.artifact_sha256, hashlib.sha256(self.artifact).hexdigest())
        self.assertEqual((value.version, value.slot_count, value.batch_size), (3, 10, 2))
        self.assertEqual((value.not_before_unix_s, value.expires_unix_s), (1000, 2000))
        self.assertEqual(value.states, ("pending",) * 10)
        self.assertEqual(self.store.read(), FleetFloors(3, 1001))

    def test_artifact_tampering_does_not_create_plan_or_advance_floors(self):
        (self.bundle / "fleet-artifact.bin").write_bytes(b"tampered")
        self.reject()
        self.assertFalse(self.journal.exists())
        self.assertEqual(self.store.read(), FleetFloors(1, 900))

    def test_bad_signature_does_not_create_plan_or_advance_floors(self):
        (self.bundle / "manifest.sig").write_bytes(bytes(64))
        self.reject()
        self.assertFalse(self.journal.exists())
        self.assertEqual(self.store.read(), FleetFloors(1, 900))

    def test_source_replacement_cannot_change_snapshot_pins(self):
        module = self.module()
        original = module.load_fleet_policy
        policy_hash = hashlib.sha256((self.bundle / "fleet-policy.json").read_bytes()).hexdigest()
        snapshots = []

        def replace(*args, **kwargs):
            snapshots.append(args[0])
            value = original(*args, **kwargs)
            (self.bundle / "fleet-artifact.bin").write_bytes(b"changed after copy")
            (self.bundle / "fleet-policy.json").write_bytes(b"changed after copy")
            return value

        with patch.object(module, "load_fleet_policy", replace):
            journal = self.create()
        self.assertEqual(
            journal.snapshot().artifact_sha256, hashlib.sha256(self.artifact).hexdigest()
        )
        self.assertEqual(journal.snapshot().policy_sha256, policy_hash)
        self.assertTrue(snapshots)
        self.assertTrue(all(not path.exists() for path in snapshots))

    def test_expiry_or_clock_rollback_during_verification_leaves_no_journal(self):
        for times in ((1000, 999, 1001), (1999, 2000, 2001), (True, 1001, 1002)):
            with self.subTest(times=times):
                self.reject(times)
                self.assertFalse(self.journal.exists())
                self.assertEqual(self.store.read(), FleetFloors(1, 900))

    def test_expiry_after_floor_commit_preserves_floor_and_creates_no_journal(self):
        self.reject((1998, 1999, 2000))
        self.assertFalse(self.journal.exists())
        self.assertEqual(self.store.read(), FleetFloors(3, 1999))

    def test_floor_commit_failure_cannot_publish_journal(self):
        with patch.object(self.store, "advance", side_effect=ValueError("injected")):
            self.reject()
        self.assertFalse(self.journal.exists())
        self.assertEqual(self.store.read(), FleetFloors(1, 900))

    def test_existing_journal_never_overwritten_after_admission(self):
        self.journal.write_bytes(b"preexisting failure evidence")
        self.reject()
        self.assertEqual(self.journal.read_bytes(), b"preexisting failure evidence")
        self.assertEqual(self.store.read(), FleetFloors(3, 1001))

    def test_missing_link_extra_and_oversized_members_fail_before_floor_commit(self):
        artifact = self.bundle / "fleet-artifact.bin"
        artifact.unlink()
        self.reject()
        artifact.symlink_to(self.private)
        self.reject()
        artifact.unlink()
        with artifact.open("wb") as stream:
            stream.truncate(8 * 1024 * 1024 + 1)
        self.reject()
        artifact.write_bytes(self.artifact)
        (self.bundle / "extra").write_bytes(b"private")
        self.reject()
        self.assertFalse(self.journal.exists())
        self.assertEqual(self.store.read(), FleetFloors(1, 900))


if __name__ == "__main__":
    unittest.main()
