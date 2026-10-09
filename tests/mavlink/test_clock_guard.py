"""Bounded clock-monitor leases; synthetic clocks and no hardware claims."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aethron_edge.telemetry import boot_authority as api
from aethron_edge.telemetry.signing import SigningTrust, provision_replay
from aethron_edge.telemetry.worker import TelemetryProfile, TelemetrySupervisor


class ClockGuardTests(unittest.TestCase):
    def setUp(self):
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
        self.trust = SigningTrust(self.policy.key, 7, 100, 1, 10_000_000_001, boot_bound=True)
        self.clock = patch.object(api.time, "monotonic_ns", return_value=1000).start()
        self.original_issue = api.issue_boot_trust
        self.issuer = patch.object(api, "issue_boot_trust", return_value=self.trust).start()
        self.addCleanup(patch.stopall)

    def guard(self):
        return api.BootClockGuard("unused", self.policy, self.trust)

    def test_check_reuses_original_grant_and_caps_freshness(self):
        guard = self.guard()
        self.assertEqual(guard.check(), 100_001_000)
        self.clock.return_value = 49_001_000
        self.assertEqual(guard.check(), 100_001_000)
        self.assertEqual(self.issuer.call_count, 1)
        self.clock.return_value = 50_001_000
        self.assertEqual(guard.check(), 150_001_000)
        self.assertEqual(self.issuer.call_count, 2)
        self.assertEqual(guard.trust, self.trust)

    def test_delayed_validation_cannot_extend_its_own_freshness(self):
        guard = self.guard()
        self.clock.side_effect = [1000, 100_001_001]
        with self.assertRaisesRegex(ValueError, "clock_authority_rejected"):
            guard.check()
        self.clock.side_effect = None
        self.clock.return_value = 2000
        with self.assertRaises(ValueError):
            guard.check()
        self.assertEqual(self.issuer.call_count, 1)

    def test_clock_rollback_invalid_values_and_expiry_latch(self):
        for now in (999, False, 1.0, 10_000_000_001):
            self.clock.return_value = 1000
            guard = self.guard()
            guard.check()
            self.clock.return_value = now
            with self.assertRaises(ValueError):
                guard.check()
            self.clock.return_value = 2000
            with self.assertRaises(ValueError):
                guard.check()

    def test_rejected_or_reanchored_authority_never_recovers(self):
        for result in (
            None,
            SigningTrust(self.trust.key, 7, 100, 1, 20_000_000_001, boot_bound=True),
        ):
            self.issuer.side_effect = None
            self.issuer.return_value = self.trust
            self.clock.return_value = 1000
            guard = self.guard()
            guard.check()
            self.clock.return_value = 50_001_000
            if result is None:
                self.issuer.side_effect = ValueError("private detail")
            else:
                self.issuer.return_value = result
            with self.assertRaisesRegex(ValueError, "^clock_authority_rejected$"):
                guard.check()
            self.issuer.side_effect = None
            self.issuer.return_value = self.trust
            with self.assertRaises(ValueError):
                guard.check()

    def test_supervisor_rejects_unbound_or_wrong_policy_without_launch(self):
        profile = TelemetryProfile(1, 2, 0, "unused")
        good = TelemetrySupervisor(profile, self.trust, clock_policy=self.policy)
        self.assertEqual(good.clock_policy, self.policy)
        for trust, policy in [
            (SigningTrust(self.trust.key, 7, 100, 1, 1000), self.policy),
            (self.trust, object()),
            (SigningTrust(bytes(32), 7, 100, 1, 1000, boot_bound=True), self.policy),
        ]:
            with self.assertRaises(ValueError):
                TelemetrySupervisor(profile, trust, clock_policy=policy)
        with self.assertRaises(ValueError):
            TelemetrySupervisor(
                TelemetryProfile(1, 3, 0, "unused"), self.trust, clock_policy=self.policy
            )

    def test_real_journal_clock_jump_is_persistently_revoked(self):
        wall = [api.MAVLINK_EPOCH_NS + 50_000_000_000]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.db"
            provision_replay(path, self.trust, system=1, component=2)
            api.provision_boot_authority(path, self.policy)

            def issue(path, policy):
                return self.original_issue(
                    path,
                    policy,
                    monotonic=lambda: self.clock.return_value,
                    realtime=lambda: wall[0],
                    boot_id=lambda: "aeeeeeee-1111-4111-8111-111111111111",
                )

            self.issuer.side_effect = issue
            grant = issue(path, self.policy)
            guard = api.BootClockGuard(path, self.policy, grant)
            guard.check()
            self.clock.return_value += 50_000_000
            wall[0] += 52_000_000
            with self.assertRaisesRegex(ValueError, "clock_authority_rejected"):
                guard.check()
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(
                    connection.execute("SELECT revoked FROM boot_authority").fetchone(), (1,)
                )
            wall[0] -= 2_000_000
            with self.assertRaises(ValueError):
                issue(path, self.policy)

    def test_worker_caps_observation_at_clock_check_deadline(self):
        from aethron_edge.telemetry import worker

        stop = Mock()
        stop.is_set.side_effect = [False, True]
        channel = Mock()
        source = Mock(max_decode_ms=0, max_commit_ms=0)
        receiver = Mock(port=1234)
        receiver.poll.return_value = SimpleNamespace(
            reason="unmapped_source_clock",
            samples=[SimpleNamespace(authenticated=True, receive_ns=1000)],
        )
        with (
            patch.object(worker.os, "dup2"),
            patch.object(worker, "_MeasuredTelemetry", return_value=source),
            patch.object(worker, "UdpTelemetry") as udp,
            patch.object(worker, "BootClockGuard") as guard,
        ):
            udp.return_value.__enter__.return_value = receiver
            guard.return_value.check.return_value = 1500
            worker._worker(
                TelemetryProfile(1, 2, 0, "unused"), self.trust, channel, stop, self.policy
            )
        self.assertEqual(channel.put_nowait.call_args.args[0]["expires_ns"], 1500)
        self.assertEqual(channel.put_nowait.call_args.args[0]["state"], "observed_unverified")
        source.close.assert_called_once()

    def test_worker_refuses_poll_on_invalid_clock_authority(self):
        from aethron_edge.telemetry import worker

        stop = Mock()
        stop.is_set.return_value = False
        channel = Mock()
        source = Mock(max_decode_ms=0, max_commit_ms=0)
        receiver = Mock(port=1234)
        with (
            patch.object(worker.os, "dup2"),
            patch.object(worker, "_MeasuredTelemetry", return_value=source),
            patch.object(worker, "UdpTelemetry") as udp,
            patch.object(worker, "BootClockGuard") as guard,
        ):
            udp.return_value.__enter__.return_value = receiver
            guard.return_value.check.side_effect = ValueError("private detail")
            worker._worker(
                TelemetryProfile(1, 2, 0, "unused"), self.trust, channel, stop, self.policy
            )
        receiver.poll.assert_not_called()
        message = channel.put_nowait.call_args.args[0]
        self.assertEqual(message["source_reason"], "clock_authority_rejected")
        self.assertEqual(message["state"], "fault")
        self.assertNotIn("private detail", repr(message))
        source.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
