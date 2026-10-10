"""Recorded-worker disclosure controls; no physical or timing qualification."""

import traceback
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aethron_edge.sensors.worker import replay_worker


class SensorWorkerClaims(unittest.TestCase):
    def test_manifest_failure_emits_only_fixed_diagnostic(self):
        messages = []
        profile = SimpleNamespace(sensor_manifest="private-manifest.json")
        with (
            patch(
                "aethron_edge.sensors.worker.load_manifest",
                side_effect=RuntimeError("private-detail"),
            ),
            patch("aethron_edge.sensors.worker.time.monotonic_ns", return_value=123),
        ):
            replay_worker(profile, messages.append, Mock())
        self.assertEqual(
            messages,
            [
                {
                    "data": None,
                    "reason": "source_lost",
                    "latency_ms": 0.0,
                    "sensor_state": "fault",
                    "sensor_batches": 0,
                    "sensor_expires_ns": 0,
                    "sensor_emitted_ns": 123,
                }
            ],
        )
        self.assertNotIn("private", repr(messages))

    def test_unavailable_diagnostic_sink_is_not_silently_reported_successful(self):
        profile = SimpleNamespace(sensor_manifest="private-manifest.json")
        send = Mock(side_effect=BrokenPipeError("closed diagnostic sink"))
        with patch(
            "aethron_edge.sensors.worker.load_manifest", side_effect=ValueError("private-detail")
        ):
            with self.assertRaises(BrokenPipeError):
                replay_worker(profile, send, Mock())
        send.assert_called_once()
        self.assertIsNone(send.call_args.args[0]["data"])
        self.assertEqual(send.call_args.args[0]["sensor_expires_ns"], 0)

    def test_failed_fault_sink_retains_private_exception_context(self):
        profile = SimpleNamespace(sensor_manifest="private-manifest.json")
        original = ValueError("private-original-sentinel")
        sink_failure = BrokenPipeError("private-sink-sentinel")
        send = Mock(side_effect=sink_failure)
        rendered = None
        with patch("aethron_edge.sensors.worker.load_manifest", side_effect=original):
            try:
                replay_worker(profile, send, Mock())
            except BrokenPipeError as error:
                self.assertIs(error, sink_failure)
                self.assertIs(error.__context__, original)
                rendered = "".join(traceback.format_exception(error))
            else:
                self.fail("sink failure was hidden")
        self.assertIn("private-original-sentinel", rendered)
        self.assertIn("private-sink-sentinel", rendered)
        send.assert_called_once()
        self.assertNotIn("private", repr(send.call_args.args[0]))

    def test_interrupt_propagates_without_claiming_final_fault_delivery(self):
        profile = SimpleNamespace(sensor_manifest="private-manifest.json")
        send = Mock()
        interrupted = KeyboardInterrupt("private-interrupt-sentinel")
        with patch("aethron_edge.sensors.worker.load_manifest", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt) as result:
                replay_worker(profile, send, Mock())
        self.assertIs(result.exception, interrupted)
        send.assert_not_called()
