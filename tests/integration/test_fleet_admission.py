"""Real signed policies and persistent floors; no deployment side effects."""

import sqlite3
import unittest
from unittest.mock import patch

import test_fleet_policy as fixtures
from aethron_edge.runtime import fleet_policy
from aethron_edge.runtime.fleet_floors import FleetFloors, FleetFloorStore


class FleetAdmissionTests(unittest.TestCase):
    run_crypto = fixtures.FleetPolicyTests.run_crypto
    sign = fixtures.FleetPolicyTests.sign

    def setUp(self):
        fixtures.FleetPolicyTests.setUp(self)
        self.store = FleetFloorStore.initialize(
            self.root / "floors.db", minimum_version=1, minimum_time_s=900
        )
        self.sign()

    def admit(self, times=(1000, 1001, 1002)):
        samples = iter(times)
        return fleet_policy.admit_fleet_policy(
            self.bundle, self.public, floor_store=self.store, clock=lambda: next(samples)
        )

    def rejected(self, times=(1000, 1001)):
        with self.assertRaisesRegex(ValueError, "^invalid_fleet_admission$"):
            self.admit(times)

    def test_admission_commits_authenticated_version_and_verified_time_before_return(self):
        self.assertTrue(callable(getattr(fleet_policy, "admit_fleet_policy", None)))
        value = self.admit()
        self.assertEqual((value.bundle_version, value.batch_size), (3, 2))
        self.assertEqual(FleetFloorStore(self.store.path).read(), FleetFloors(3, 1001))

    def test_restart_rejects_valid_signature_below_committed_version(self):
        self.admit()
        self.store = FleetFloorStore(self.store.path)
        self.sign(fixtures.policy(bundle_version=2), version=2)
        self.rejected((1002, 1003))
        self.assertEqual(self.store.read(), FleetFloors(3, 1001))

    def test_unauthenticated_bytes_cannot_advance_either_floor(self):
        (self.bundle / "manifest.sig").write_bytes(bytes(64))
        self.rejected()
        self.assertEqual(self.store.read(), FleetFloors(1, 900))

    def test_clock_rollback_before_or_during_verification_preserves_floors(self):
        for times in ((899, 1000), (1001, 1000)):
            with self.subTest(times=times):
                self.rejected(times)
                self.assertEqual(self.store.read(), FleetFloors(1, 900))

    def test_expiry_during_verification_rejects_without_committing(self):
        self.rejected((1999, 2000))
        self.assertEqual(self.store.read(), FleetFloors(1, 900))

    def test_expiry_during_commit_rejects_but_retains_committed_floors(self):
        self.rejected((1998, 1999, 2000))
        self.assertEqual(self.store.read(), FleetFloors(3, 1999))

    def test_invalid_or_backward_post_commit_time_never_returns_configuration(self):
        for bad in (True, 1002.0, None, -1, 2**53, 1000):
            with self.subTest(time=bad):
                self.rejected((1001, 1001, bad))
                self.assertEqual(self.store.read(), FleetFloors(3, 1001))

    def test_post_commit_clock_failure_retains_floors(self):
        self.rejected((1000, 1001))
        self.assertEqual(self.store.read(), FleetFloors(3, 1001))

    def test_clock_provider_errors_at_each_sample_do_not_retry_or_echo_details(self):
        for error_type in (OSError, RuntimeError, ValueError):
            for failed_sample in range(3):
                with self.subTest(error=error_type.__name__, sample=failed_sample):
                    store = FleetFloorStore.initialize(
                        self.root / f"{error_type.__name__}-{failed_sample}.db",
                        minimum_version=1,
                        minimum_time_s=900,
                    )
                    calls = []

                    def clock(*, failure=failed_sample, exception=error_type, observed=calls):
                        index = len(observed)
                        observed.append(index)
                        if index == failure:
                            raise exception("private clock provider details")
                        return (1000, 1001, 1002)[index]

                    with self.assertRaisesRegex(ValueError, "^invalid_fleet_admission$"):
                        fleet_policy.admit_fleet_policy(
                            self.bundle, self.public, floor_store=store, clock=clock
                        )
                    self.assertEqual(len(calls), failed_sample + 1)
                    expected = FleetFloors(3, 1001) if failed_sample == 2 else FleetFloors(1, 900)
                    self.assertEqual(FleetFloorStore(store.path).read(), expected)

    def test_final_clock_observes_commit_before_return(self):
        samples = iter((1000, 1001, 1999))
        observed = []

        def clock():
            value = next(samples)
            observed.append(FleetFloorStore(self.store.path).read())
            return value

        value = fleet_policy.admit_fleet_policy(
            self.bundle, self.public, floor_store=self.store, clock=clock
        )
        self.assertEqual(value.bundle_version, 3)
        self.assertEqual(observed, [FleetFloors(1, 900), FleetFloors(1, 900), FleetFloors(3, 1001)])

    def test_invalid_time_samples_never_advance_floors(self):
        for bad in (True, 1000.0, None, -1, 2**53):
            for times in ((bad, 1001), (1000, bad)):
                with self.subTest(times=times):
                    self.rejected(times)
                    self.assertEqual(self.store.read(), FleetFloors(1, 900))

    def test_competing_version_advance_wins_over_stale_admission(self):
        original = fleet_policy.load_fleet_policy

        def competing_writer(*args, **kwargs):
            value = original(*args, **kwargs)
            FleetFloorStore(self.store.path).advance(minimum_version=4, minimum_time_s=1000)
            return value

        with patch.object(fleet_policy, "load_fleet_policy", competing_writer):
            self.rejected()
        self.assertEqual(self.store.read(), FleetFloors(4, 1000))

    def test_competing_time_advance_wins_over_stale_admission(self):
        original = fleet_policy.load_fleet_policy

        def competing_writer(*args, **kwargs):
            value = original(*args, **kwargs)
            FleetFloorStore(self.store.path).advance(minimum_version=1, minimum_time_s=1002)
            return value

        with patch.object(fleet_policy, "load_fleet_policy", competing_writer):
            self.rejected()
        self.assertEqual(self.store.read(), FleetFloors(1, 1002))

    def test_failed_commit_never_returns_admitted_configuration(self):
        original = sqlite3.connect

        class FailingCommit(sqlite3.Connection):
            def execute(self, statement, parameters=()):
                if statement == "COMMIT":
                    raise sqlite3.OperationalError("injected commit failure")
                return super().execute(statement, parameters)

        def connect(*args, **kwargs):
            return original(*args, factory=FailingCommit, **kwargs)

        with patch("aethron_edge.runtime.fleet_floors.sqlite3.connect", connect):
            self.rejected()
        self.assertEqual(self.store.read(), FleetFloors(1, 900))

    def test_missing_store_never_reinitializes_at_admission(self):
        self.store.path.unlink()
        self.rejected()
        self.assertFalse(self.store.path.exists())

    def test_idempotent_version_still_commits_newer_time(self):
        self.admit()
        self.admit((1002, 1003, 1004))
        self.assertEqual(self.store.read(), FleetFloors(3, 1003))


if __name__ == "__main__":
    unittest.main()
