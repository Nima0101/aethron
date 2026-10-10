"""Fresh signed checks and serialized floors before synthetic wave reservation."""

import hashlib
import json
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import test_fleet_plan as fixtures
from aethron_edge.runtime import fleet_plan
from aethron_edge.runtime.fleet_floors import FleetFloors, FleetFloorStore


class FleetClaimTests(unittest.TestCase):
    run_crypto = fixtures.FleetPlanTests.run_crypto
    sign = fixtures.FleetPlanTests.sign

    def setUp(self):
        fixtures.FleetPlanTests.setUp(self)
        samples = iter((1000, 1001, 1002, 1002))
        self.plan = fleet_plan.create_rollout_plan(
            self.bundle,
            self.public,
            journal_path=self.journal,
            floor_store=self.store,
            clock=lambda: next(samples),
        )

    def claim(self, times=(1003, 1004, 1005, 1006), **changes):
        self.assertTrue(callable(getattr(fleet_plan, "claim_rollout_wave", None)))
        samples = iter(times)
        options = {
            "journal": self.plan,
            "floor_store": self.store,
            "clock": lambda: next(samples),
            "expected_revision": 0,
            "provisioning": False,
        }
        options.update(changes)
        return fleet_plan.claim_rollout_wave(self.bundle, self.public, **options)

    def reject(self, *args, **kwargs):
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_claim$"):
            self.claim(*args, **kwargs)

    def test_reverified_claim_commits_wave_and_floor_before_return(self):
        self.assertEqual(self.claim(), (0, 1))
        self.assertEqual(self.plan.snapshot().states, ("running",) * 2 + ("pending",) * 8)
        self.assertEqual(self.store.read(), FleetFloors(3, 1004))

    def test_mutated_source_and_revoked_key_cannot_claim_existing_plan(self):
        (self.bundle / "fleet-artifact.bin").write_bytes(b"changed")
        self.reject()
        (self.bundle / "fleet-artifact.bin").write_bytes(self.artifact)
        self.run_crypto("genpkey", "-algorithm", "ED25519", "-out", str(self.private))
        self.run_crypto("pkey", "-in", str(self.private), "-pubout", "-out", str(self.public))
        self.reject()
        self.assertEqual(self.plan.snapshot().revision, 0)

    def test_floor_advanced_after_snapshot_verification_blocks_claim(self):
        original = fleet_plan.load_fleet_policy

        def newer(*args, **kwargs):
            value = original(*args, **kwargs)
            self.store.advance(minimum_version=4, minimum_time_s=1004)
            return value

        with patch.object(fleet_plan, "load_fleet_policy", newer):
            self.reject()
        self.assertEqual(self.plan.snapshot().revision, 0)
        self.assertEqual(self.store.read(), FleetFloors(4, 1004))

    def test_floor_lock_covers_the_journal_reservation(self):
        original = self.plan.claim

        def compete(**kwargs):
            with self.assertRaisesRegex(ValueError, "invalid_fleet_floor"):
                FleetFloorStore(self.store.path).advance(minimum_version=4, minimum_time_s=1005)
            return original(**kwargs)

        with patch.object(self.plan, "claim", compete):
            self.assertEqual(self.claim(), (0, 1))
        self.assertEqual(self.store.read().minimum_version, 3)

    def test_post_reservation_floor_commit_failure_returns_no_claim(self):
        original = sqlite3.connect

        class FailFloorCommit(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql == "COMMIT":
                    raise sqlite3.OperationalError("injected")
                return super().execute(sql, parameters)

        def connect(path, **kwargs):
            if "floors.db" in str(path):
                kwargs["factory"] = FailFloorCommit
            return original(path, **kwargs)

        with patch("aethron_edge.runtime.fleet_floors.sqlite3.connect", connect):
            self.reject()
        self.assertEqual(self.store.read(), FleetFloors(3, 1001))
        self.assertEqual(self.plan.snapshot().revision, 1)
        self.reject(expected_revision=1)
        self.assertEqual(self.plan.snapshot().states[:2], ("running", "running"))

    def test_expiry_before_reservation_and_after_reservation_fail_closed(self):
        self.reject((1998, 1999, 2000, 2001))
        self.assertEqual(self.plan.snapshot().revision, 0)
        self.reject((1997, 1998, 1999, 2000))
        self.assertEqual(self.plan.snapshot().revision, 1)
        self.assertEqual(self.store.read(), FleetFloors(3, 1001))

    def test_provisioning_requires_explicit_signed_permission_and_strict_flag(self):
        for flag in (True, 1, "false", None):
            self.reject(provisioning=flag)
        self.assertEqual(self.plan.snapshot().revision, 0)

    def test_stale_journal_revision_cannot_claim_and_rolls_back_floor_write(self):
        self.reject(expected_revision=1)
        self.assertEqual(self.store.read(), FleetFloors(3, 1001))
        self.assertEqual(self.plan.snapshot().revision, 0)

    def test_journal_bound_fields_must_match_authenticated_policy(self):
        with closing(sqlite3.connect(self.journal)) as db, db:
            value = json.loads(db.execute("SELECT payload FROM rollout").fetchone()[0])
            value["batch_size"] = 3
            db.execute("UPDATE rollout SET payload=?", (json.dumps(value),))
        self.reject()
        self.assertEqual(self.plan.snapshot().revision, 0)

    def resign_policy(self, **changes):
        path = self.bundle / "fleet-policy.json"
        value = json.loads(path.read_text())
        value.update(changes)
        path.write_text(json.dumps(value))
        manifest_path = self.bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["files"]["fleet-policy.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        self.run_crypto(
            "pkeyutl",
            "-sign",
            "-rawin",
            "-inkey",
            str(self.private),
            "-in",
            str(manifest_path),
            "-out",
            str(self.bundle / "manifest.sig"),
        )

    def test_signed_provisioning_permission_allows_only_a_synthetic_reservation(self):
        self.resign_policy(allow_initial_provisioning=True)
        samples = iter((1003, 1004, 1005, 1005))
        self.plan = fleet_plan.create_rollout_plan(
            self.bundle,
            self.public,
            journal_path=self.root / "provision.db",
            floor_store=self.store,
            clock=lambda: next(samples),
        )
        self.assertEqual(self.claim((1006, 1007, 1008, 1009), provisioning=True), (0, 1))
        self.assertEqual(self.plan.snapshot().revision, 1)

    def test_same_version_signed_policy_change_cannot_rebind_an_existing_plan(self):
        self.resign_policy(batch_size=3)
        self.reject()
        self.assertEqual(self.plan.snapshot().revision, 0)
        self.assertEqual(self.store.read(), FleetFloors(3, 1001))


if __name__ == "__main__":
    unittest.main()
