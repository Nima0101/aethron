"""Bounded aggregate telemetry timing; never grants observation authority."""

import multiprocessing as mp
import unittest
from unittest.mock import Mock, patch

from aethron_edge.telemetry import worker
from aethron_edge.telemetry.signing import SigningTrust


class TimingTests(unittest.TestCase):
    def measured(self):
        with patch.object(worker.SignedTelemetry, "__init__", return_value=None):
            return worker._MeasuredTelemetry()

    def test_decode_and_commit_have_separate_ceiling_rounded_peaks(self):
        source = self.measured()
        with (
            patch.object(worker.SignedTelemetry, "_decode_packet", return_value="decoded"),
            patch.object(worker.SignedTelemetry, "_commit_packet", return_value=True),
            patch.object(
                worker.time, "monotonic_ns", side_effect=[0, 1, 2, 1_500_003, 2_000_000, 2_000_001]
            ),
        ):
            self.assertEqual(source._decode_packet(b"", 0), "decoded")
            self.assertTrue(source._commit_packet(b""))
            self.assertTrue(source._commit_packet(b""))
        self.assertEqual(source.max_decode_ms, 1)
        self.assertEqual(source.max_commit_ms, 2)

    def test_failed_operation_is_measured_and_capped_without_swallowing_error(self):
        source = self.measured()
        with (
            patch.object(
                worker.SignedTelemetry, "_commit_packet", side_effect=ValueError("failure")
            ),
            patch.object(worker.time, "monotonic_ns", side_effect=[0, 90_000_000_000]),
            self.assertRaisesRegex(ValueError, "failure"),
        ):
            source._commit_packet(b"")
        self.assertEqual(source.max_commit_ms, 60000)
        self.assertEqual(source.max_decode_ms, 0)

    def supervisor(self):
        result = worker.TelemetrySupervisor(
            worker.TelemetryProfile(1, 1, 0, "unused"),
            SigningTrust(bytes(32), 1, 100, 1, 500_000_000_000),
        )
        result._started_ns = 1
        result.process = Mock()
        result.process.is_alive.return_value = True
        read, write = mp.Pipe(duplex=False)
        self.addCleanup(read.close)
        self.addCleanup(write.close)
        result.process.sentinel = read.fileno()
        result._channel = Mock()
        return result

    def message(self):
        return {
            "state": "observed_unverified",
            "port": 1234,
            "samples": 1,
            "expires_ns": 100_000_100,
            "emitted_ns": 100,
            "source_reason": "unmapped_source_clock",
            "max_poll_ms": 12,
            "max_decode_ms": 1,
            "max_commit_ms": 3,
        }

    def test_delivery_delay_is_reported_but_expired_message_stays_unauthenticated(self):
        supervisor = self.supervisor()
        supervisor._channel.get_nowait.return_value = self.message()
        with patch.object(worker.time, "monotonic_ns", return_value=250_000_100):
            supervisor._consume(1)
            status = supervisor.snapshot()
        self.assertEqual(status["max_delivery_ms"], 250)
        self.assertEqual(status["max_commit_ms"], 3)
        self.assertEqual(status["max_decode_ms"], 1)
        self.assertFalse(status["authenticated"])
        self.assertEqual(status["samples"], 0)
        self.assertFalse(status["perception_eligible"])

    def test_untrusted_timing_fields_fail_closed(self):
        for field in ("max_decode_ms", "max_commit_ms"):
            for value in (-1, 60001, True, 1.0, "1"):
                with self.subTest(field=field, value=value):
                    supervisor = self.supervisor()
                    message = self.message()
                    message[field] = value
                    supervisor._channel.get_nowait.return_value = message
                    with patch.object(worker.time, "monotonic_ns", return_value=101):
                        supervisor._consume(1)
                        status = supervisor.snapshot()
                    self.assertEqual(status["reason"], "worker_protocol")
                    self.assertFalse(status["authenticated"])

    def test_delivery_counters_distinguish_observed_from_already_expired(self):
        supervisor = self.supervisor()
        supervisor._channel.get_nowait.return_value = self.message()
        with patch.object(worker.time, "monotonic_ns", return_value=101):
            supervisor._consume(1)
        with patch.object(worker.time, "monotonic_ns", return_value=200_000_100):
            supervisor._consume(1)
            status = supervisor.snapshot()
        self.assertEqual(status["messages_received"], 2)
        self.assertEqual(status["observed_messages"], 2)
        self.assertEqual(status["expired_on_arrival"], 1)
        self.assertEqual(status["message_age_ms"], 200)
        self.assertEqual(status["message_state"], "observed_unverified")
        self.assertFalse(status["authenticated"])

    def test_invalid_messages_do_not_contribute_to_diagnostics(self):
        supervisor = self.supervisor()
        message = self.message()
        message["samples"] = True
        supervisor._channel.get_nowait.return_value = message
        with patch.object(worker.time, "monotonic_ns", return_value=101):
            supervisor._consume(1)
            status = supervisor.snapshot()
        self.assertEqual(status["messages_received"], 0)
        self.assertIsNone(status["message_age_ms"])
        self.assertEqual(status["message_state"], "none")

    def test_diagnostic_counters_saturate_without_extending_freshness(self):
        supervisor = self.supervisor()
        supervisor._messages_received = supervisor._observed_messages = 2**31 - 1
        supervisor._expired_on_arrival = 2**31 - 1
        supervisor._channel.get_nowait.return_value = self.message()
        with patch.object(worker.time, "monotonic_ns", return_value=100_000_000_100):
            supervisor._consume(1)
            status = supervisor.snapshot()
        for name in ("messages_received", "observed_messages", "expired_on_arrival"):
            self.assertEqual(status[name], 2**31 - 1)
        self.assertEqual(status["message_age_ms"], 60000)
        self.assertFalse(status["authenticated"])

    def test_owner_scheduling_gap_is_measured_without_counting_initial_anchor_age(self):
        supervisor = self.supervisor()
        supervisor._stop = Mock()
        supervisor._stop.is_set.side_effect = [False, False, True]
        with (
            patch.object(supervisor, "_consume"),
            patch.object(supervisor, "_retire"),
            patch.object(worker, "wait", return_value=[]),
            patch.object(
                worker.time, "monotonic_ns", side_effect=[100, 101, 25_000_101, 25_000_102]
            ),
        ):
            supervisor._run()
        supervisor._stop.is_set.side_effect = None
        supervisor._stop.is_set.return_value = False
        with patch.object(worker.time, "monotonic_ns", return_value=25_000_103):
            self.assertEqual(supervisor.snapshot()["max_owner_gap_ms"], 26)

    def test_live_worker_waits_for_process_exit_without_condition_timer(self):
        supervisor = self.supervisor()
        supervisor.process.sentinel = 42
        supervisor._stop = Mock()
        supervisor._stop.is_set.side_effect = [False, True]
        with (
            patch.object(supervisor, "_consume"),
            patch.object(supervisor, "_retire"),
            patch.object(worker.time, "monotonic_ns", return_value=100),
            patch.object(worker, "wait", create=True, return_value=[]) as wait,
        ):
            supervisor._run()
        wait.assert_called_once_with([42], timeout=0.01)
        supervisor._stop.wait.assert_not_called()

    def test_ready_exit_sentinel_withdraws_status_even_if_liveness_check_is_stale(self):
        supervisor = self.supervisor()
        read, write = mp.Pipe(duplex=False)
        self.addCleanup(read.close)
        write.close()
        supervisor.process.sentinel = read.fileno()
        supervisor._message = self.message()
        with patch.object(worker.time, "monotonic_ns", return_value=101):
            self.assertFalse(supervisor.snapshot()["authenticated"])


if __name__ == "__main__":
    unittest.main()
