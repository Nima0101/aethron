"""Replay workers validate bounded input completely before publishing any frame."""

import io
import json
import queue
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron_edge.config import Profile
from aethron_edge.pipeline import _worker

ROOT = Path(__file__).resolve().parents[2]


class BoundedInput(io.BytesIO):
    def __init__(self, data, on_read=None):
        super().__init__(data)
        self.consumed = 0
        self.on_read = on_read

    def read(self, *args):
        raise AssertionError("unbounded replay preload")

    def readline(self, size=-1):
        if not 0 < size <= 65537:
            raise AssertionError("unbounded replay line")
        line = super().readline(size)
        self.consumed += len(line)
        if self.on_read:
            self.on_read()
        return line


class Stop:
    def __init__(self, frames=3):
        self.remaining = frames

    def is_set(self):
        return self.remaining <= 0

    def wait(self, timeout):
        self.remaining -= 1
        return self.is_set()


class WorkerReplayInput(unittest.TestCase):
    def run_worker(self, stream, stop=None):
        channel = queue.SimpleQueue()
        with (
            patch("aethron_edge.pipeline.own_descendants"),
            patch.object(Path, "open", return_value=stream),
            patch("aethron_edge.pipeline.time.monotonic_ns", return_value=10_000_000_000),
        ):
            _worker(
                Profile(
                    name="bounded", driver="replay", address="test-input", contract="drone_hover"
                ),
                channel,
                stop or Stop(),
                None,
                None,
                None,
            )
        messages = []
        while not channel.empty():
            messages.append(channel.get_nowait())
        self.assertTrue(stream.closed)
        return messages

    def test_bounded_preload_preserves_rebased_frames(self):
        data = (ROOT / "examples/temporal-blackout.jsonl").read_bytes()
        stream = BoundedInput(data)
        messages = self.run_worker(stream)
        self.assertEqual(len(messages), 3)
        for index, message in enumerate(messages):
            expected = json.loads(data.splitlines()[index])
            delta = 10000 - expected["at_ms"]
            expected.update(at_ms=10000, contract="drone_hover", scene_break=index == 0)
            for sensor in expected["sensors"]:
                sensor["at_ms"] += delta
                sensor["calibration_until_ms"] += delta
            self.assertEqual(json.loads(message["data"]), expected)
        self.assertEqual(stream.consumed, len(data))

    def test_oversized_line_stops_reading_at_core_limit(self):
        stream = BoundedInput(b" " * 200000)
        messages = self.run_worker(stream)
        self.assertEqual(stream.consumed, 65537)
        self.assertEqual(messages, [{"data": None, "reason": "model_error", "latency_ms": 0}])

    def test_bad_tail_never_publishes_valid_prefix(self):
        data = (ROOT / "examples/temporal-blackout.jsonl").read_bytes()
        for tail in (b"private-sentinel", b" " * 65537):
            with self.subTest(length=len(tail)):
                messages = self.run_worker(BoundedInput(data + tail))
                self.assertEqual(
                    messages, [{"data": None, "reason": "model_error", "latency_ms": 0}]
                )

    def test_empty_and_301_frames_never_activate(self):
        frame = json.loads((ROOT / "examples/temporal-blackout.jsonl").read_bytes().splitlines()[0])
        rows = []
        for index in range(301):
            frame["at_ms"] = index
            rows.append(json.dumps(frame).encode() + b"\n")
        bounded_prefix = b"".join(rows)
        for data in (b"", bounded_prefix + b"unread-private-tail"):
            stream = BoundedInput(data)
            messages = self.run_worker(stream)
            self.assertEqual(messages, [{"data": None, "reason": "model_error", "latency_ms": 0}])
            self.assertEqual(stream.consumed, len(bounded_prefix) if data else 0)

    def test_cancellation_during_validation_does_not_read_remaining_file(self):
        data = (ROOT / "examples/temporal-blackout.jsonl").read_bytes()
        stop = Stop()
        stream = BoundedInput(data, on_read=lambda: setattr(stop, "remaining", 0))
        messages = self.run_worker(stream, stop)
        self.assertEqual(stream.consumed, len(data.splitlines(keepends=True)[0]))
        self.assertTrue(all(message["data"] is None for message in messages))
