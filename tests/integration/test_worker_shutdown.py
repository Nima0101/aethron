"""Stopping a worker retires its scene even when process cleanup fails."""

import json
import queue
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aethron_edge.config import Profile
from aethron_edge.pipeline import RuntimePipeline

ROOT = Path(__file__).resolve().parents[2]


class WorkerShutdown(unittest.TestCase):
    def setUp(self):
        with patch("aethron_edge.pipeline.time.monotonic_ns", return_value=1_000_000_000):
            self.runtime = RuntimePipeline(
                Profile(name="shutdown", driver="replay", address="unused", contract="vehicle_stop")
            )
        self.process = Mock(pid=12345)
        self.process.is_alive.return_value = False
        self.runtime.process = self.process
        self.runtime.stop = Mock()
        self.runtime.group = SimpleNamespace(value=0)
        self.runtime.channel = queue.SimpleQueue()
        for at_ms in (1001, 1002):
            self.runtime.channel.put_nowait(self.message(at_ms))
            result = self.runtime.tick(at_ms * 1_000_000)
        self.assertEqual(result["state"], "PRESENT")
        self.assertEqual(len(result["tracks"]), 1)
        self.old_id = result["tracks"][0]["id"]
        self.recommendation = result["recommendation"]

    def tearDown(self):
        self.process.join.side_effect = None
        if isinstance(self.runtime.stop, Mock):
            self.runtime.stop.set.side_effect = None
        self.runtime.close()

    def message(self, at_ms):
        frame = json.loads((ROOT / "examples/temporal-blackout.jsonl").read_bytes().splitlines()[0])
        delta = at_ms - frame["at_ms"]
        frame["at_ms"] = at_ms
        for sensor in frame["sensors"]:
            sensor["at_ms"] += delta
            sensor["calibration_until_ms"] += delta
        return {"data": json.dumps(frame).encode(), "reason": None, "latency_ms": 0}

    def assert_retired(self):
        result = self.runtime.snapshot(1_002_000_000)
        self.assertEqual(result["state"], "UNKNOWN")
        self.assertEqual(result["tracks"], [])
        self.assertIsNone(result["evidence"])
        self.assertEqual(result["recommendation"], self.recommendation)

    def test_stop_erases_scene_before_process_cleanup(self):
        self.runtime.stop.set.side_effect = self.assert_retired
        self.process.join.side_effect = lambda **kwargs: self.assert_retired()
        self.runtime.stop_worker()
        self.assert_retired()
        self.process.close.assert_called_once()
        self.assertIsNone(self.runtime.process)

    def test_failed_close_erases_scene_and_rejects_pending_frame(self):
        self.process.join.side_effect = OSError("cleanup unavailable")
        self.runtime.channel.put_nowait(self.message(1003))
        with self.assertRaisesRegex(OSError, "^cleanup unavailable$"):
            self.runtime.close()
        self.assertIs(self.runtime.process, self.process)
        self.process.close.assert_not_called()
        self.assert_retired()
        late = self.runtime.tick(1_003_000_000)
        self.assertEqual(late["state"], "UNKNOWN")
        self.assertEqual(late["tracks"], [])
        self.assertIsNone(late["evidence"])
        self.process.join.side_effect = None
        self.runtime.close()
        self.runtime.close()
        self.process.close.assert_called_once()

    def test_restart_creates_new_scene_and_accepts_new_evidence(self):
        self.runtime.stop_worker()
        self.assert_retired()
        # Exercise actual start/mailbox/core replacement without spawning a
        # child: replay content is supplied through the new mailbox explicitly.
        with (
            patch("multiprocessing.process.BaseProcess.start"),
            patch("aethron_edge.pipeline.time.monotonic_ns", return_value=1_002_000_000),
        ):
            self.runtime.start()
        self.runtime.channel.put_nowait(self.message(1003))
        result = self.runtime.tick(1_003_000_000)
        self.assertEqual(result["state"], "PRESENT")
        self.assertEqual(len(result["tracks"]), 1)
        self.assertNotEqual(result["tracks"][0]["id"], self.old_id)
        self.assertEqual(result["evidence"], "synthetic")
