"""Offline clock policy and durable idempotency, with synthetic clocks/keys."""

import importlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from aethron_edge.telemetry.signing import SignedTelemetry, SigningTrust, provision_replay
from pymavlink.dialects.v20 import common

BOOT1 = "aeeeeeee-1111-4111-8111-111111111111"
BOOT2 = "beeeeeee-1111-4111-8111-111111111111"


class BootAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("aethron_edge.telemetry.boot_authority")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "replay.db"
        self.mono = 1_000_000_000
        self.wall = self.api.MAVLINK_EPOCH_NS + 100_000_000_000
        self.boot = BOOT1
        self.policy = self.api.BootClockPolicy(
            key=bytes(range(32)),
            system_id=1,
            component_id=1,
            link_id=7,
            not_before_unix_ns=self.wall - 1_000_000_000,
            not_after_unix_ns=self.wall + 300_000_000_000,
            lease_ns=60_000_000_000,
            drift_budget_ns=1_000_000,
        )
        provision_replay(
            self.path, SigningTrust(self.policy.key, 7, 0, 1, 2), system=1, component=1
        )
        self.api.provision_boot_authority(self.path, self.policy)

    def issue(self):
        return self.api.issue_boot_trust(
            self.path,
            self.policy,
            monotonic=lambda: self.mono,
            realtime=lambda: self.wall,
            boot_id=lambda: self.boot,
        )

    def counter(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute("SELECT timestamp FROM replay").fetchone()[0]

    def test_first_boot_and_repeated_service_start_reuse_deadline_without_reset(self):
        grant = self.issue()
        self.assertEqual(grant.timestamp_floor, 10_000_000)
        self.assertEqual(grant.issued_ns, self.mono)
        self.assertEqual(grant.valid_until_ns, self.mono + self.policy.lease_ns)
        self.mono += 10_000_000
        self.wall += 10_000_000
        self.assertEqual(self.issue(), grant)
        self.assertEqual(self.counter(), 0)
        self.assertNotIn(repr(self.policy.key), repr(self.policy))
        with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
            self.api.provision_boot_authority(self.path, self.policy)
        self.assertEqual(self.issue(), grant)

    def test_installed_fresh_process_reuses_original_grant(self):
        original = self.issue()
        program = """
import json, sys
from aethron_edge.telemetry.boot_authority import BootClockPolicy, issue_boot_trust, MAVLINK_EPOCH_NS
wall = MAVLINK_EPOCH_NS + 100_000_000_000
policy = BootClockPolicy(bytes(range(32)), 1, 1, 7, wall - 1_000_000_000,
                        wall + 300_000_000_000, 60_000_000_000, 1_000_000)
grant = issue_boot_trust(sys.argv[1], policy, monotonic=lambda: 1_010_000_000,
                        realtime=lambda: wall + 10_000_000,
                        boot_id=lambda: "aeeeeeee-1111-4111-8111-111111111111")
print(json.dumps([grant.issued_ns, grant.valid_until_ns, grant.timestamp_floor, grant.boot_bound]))
"""
        result = subprocess.run(
            [sys.executable, "-I", "-c", program, str(self.path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        self.assertEqual(
            json.loads(result.stdout),
            [original.issued_ns, original.valid_until_ns, original.timestamp_floor, True],
        )

    def test_expired_same_boot_cannot_extend_even_after_process_reconstruction(self):
        grant = self.issue()
        self.mono = grant.valid_until_ns
        self.wall += self.policy.lease_ns
        for _ in range(2):
            with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
                self.issue()
        self.assertEqual(self.counter(), 0)

    def test_new_boot_requires_advancing_trusted_time_and_keeps_replay_counter(self):
        first = self.issue()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("UPDATE replay SET timestamp=?", (first.timestamp_floor + 5,))
            connection.commit()
        self.boot = BOOT2
        self.mono = 100
        self.wall += 1_000_000_000
        second = self.issue()
        self.assertEqual(second.issued_ns, 100)
        self.assertGreater(second.timestamp_floor, first.timestamp_floor + 5)
        self.assertEqual(self.counter(), first.timestamp_floor + 5)

    def test_same_boot_clock_jump_or_rollback_latches(self):
        for delta in (-10_000_000, 10_000_000):
            with self.subTest(delta=delta):
                # Each case uses a distinct pre-provisioned journal.
                original = self.path
                self.path = original.with_name(str(delta) + ".db")
                provision_replay(
                    self.path, SigningTrust(self.policy.key, 7, 0, 1, 2), system=1, component=1
                )
                self.api.provision_boot_authority(self.path, self.policy)
                self.issue()
                self.wall += delta
                with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
                    self.issue()
                self.wall -= delta
                with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
                    self.issue()
                self.path = original

    def test_new_boot_cannot_anchor_behind_replay_or_outside_policy(self):
        grant = self.issue()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute(
                "UPDATE replay SET timestamp=?", (grant.timestamp_floor + 2_000_000,)
            )
            connection.commit()
        self.boot = BOOT2
        self.mono = 100
        self.wall += 1_000_000_000
        with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
            self.issue()
        self.wall = self.policy.not_after_unix_ns
        with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
            self.issue()

    def test_missing_state_and_changed_policy_are_not_reprovisioned(self):
        from dataclasses import replace

        self.policy = replace(self.policy, lease_ns=self.policy.lease_ns + 1)
        with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
            self.issue()
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
            self.issue()
        self.assertFalse(self.path.exists())

    def test_slow_or_reversed_clock_sample_never_issues(self):
        for after in (self.mono - 1, self.mono + 1_000_001):
            samples = iter([self.mono, after])
            with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
                self.api.issue_boot_trust(
                    self.path,
                    self.policy,
                    monotonic=lambda samples=samples: next(samples),
                    realtime=lambda: self.wall,
                    boot_id=lambda: self.boot,
                )

    def test_boolean_or_unbounded_policy_is_rejected(self):
        from dataclasses import replace

        for changes in (
            {"lease_ns": True},
            {"lease_ns": 0},
            {"drift_budget_ns": 1_000_000_001},
            {"system_id": True},
            {"not_after_unix_ns": self.wall - 2_000_000_000},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.policy, **changes)

    def test_new_boot_cannot_rollback_below_last_successful_clock_check(self):
        self.issue()
        self.wall += 10_000_000_000
        self.mono += 10_000_000_000
        self.issue()
        self.boot = BOOT2
        self.mono = 100
        self.wall -= 5_000_000_000
        with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
            self.issue()

    def test_coordinated_clock_rollback_cannot_bypass_offset_check(self):
        self.issue()
        self.wall += 10_000_000_000
        self.mono += 10_000_000_000
        self.issue()
        self.wall -= 5_000_000_000
        self.mono -= 5_000_000_000
        with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
            self.issue()

    def test_invalid_sample_revokes_existing_same_boot_authority(self):
        self.issue()
        samples = iter([self.mono, self.mono - 1])
        with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
            self.api.issue_boot_trust(
                self.path,
                self.policy,
                monotonic=lambda: next(samples),
                realtime=lambda: self.wall,
                boot_id=lambda: self.boot,
            )
        with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
            self.issue()

    def packet(self, grant, sequence):
        encoder = common.MAVLink(None, srcSystem=1, srcComponent=1)
        encoder.seq = sequence
        encoder.signing.secret_key = self.policy.key
        encoder.signing.sign_outgoing = True
        encoder.signing.link_id = self.policy.link_id
        encoder.signing.timestamp = grant.timestamp_floor + sequence + 1
        return common.MAVLink_attitude_message(10 + sequence, 0.1, 0.2, 0.3, 0, 0, 0).pack(encoder)

    def test_commit_consuming_lease_cannot_be_retried_with_earlier_clock(self):
        samples = iter([self.mono, self.mono, self.mono + self.policy.lease_ns])
        with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
            self.api.issue_boot_trust(
                self.path,
                self.policy,
                monotonic=lambda: next(samples),
                realtime=lambda: self.wall,
                boot_id=lambda: self.boot,
            )
        with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
            self.issue()

    def test_bound_receiver_refuses_reanchored_grant_and_revoked_or_missing_record(self):
        from dataclasses import replace

        grant = self.issue()
        with self.assertRaisesRegex(ValueError, "invalid_replay_store"):
            SignedTelemetry(
                1,
                1,
                trust=replace(grant, valid_until_ns=grant.valid_until_ns + 1),
                replay_path=self.path,
                clock=lambda: self.mono,
            )
        source = SignedTelemetry(1, 1, trust=grant, replay_path=self.path, clock=lambda: self.mono)
        self.addCleanup(source.close)
        source.ingest(self.packet(grant, 0))
        self.assertTrue(source.snapshot().samples)
        self.wall += 10_000_000
        with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
            self.issue()
        source.ingest(self.packet(grant, 1))
        self.assertEqual(source.snapshot().reason, "replay_store_failed")
        self.assertFalse(source.snapshot().samples)

    def test_removed_authority_record_does_not_downgrade_existing_receiver(self):
        grant = self.issue()
        source = SignedTelemetry(1, 1, trust=grant, replay_path=self.path, clock=lambda: self.mono)
        self.addCleanup(source.close)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("DROP TABLE boot_authority")
            connection.commit()
        source.ingest(self.packet(grant, 0))
        self.assertEqual(source.snapshot().reason, "replay_store_failed")
        self.assertFalse(source.snapshot().samples)
        with self.assertRaisesRegex(ValueError, "invalid_replay_store"):
            SignedTelemetry(1, 1, trust=grant, replay_path=self.path, clock=lambda: self.mono)


if __name__ == "__main__":
    unittest.main()
