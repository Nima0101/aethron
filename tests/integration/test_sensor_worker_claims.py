"""Recorded-worker disclosure controls; no physical or timing qualification."""

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
