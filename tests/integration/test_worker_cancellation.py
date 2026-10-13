"""Cooperative stop must reach active ORT calls and withdraw late results."""

import importlib.util
import multiprocessing as mp
import queue
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aethron_edge import pipeline
from aethron_edge.config import Profile
from aethron_edge.mailbox import StopToken
from aethron_edge.sources.base import FrameEnvelope, SourceFault

from aethron.vision.yolox import InferenceCancellation


class WorkerCancellation(unittest.TestCase):
    def setUp(self):
        self.stop = StopToken(mp.get_context("spawn"))
        self.channel = queue.Queue()
        self.source = Mock(drops=0)
        self.source.read.return_value = FrameEnvelope(
            bytes(12), 2, 2, 1, None, time.monotonic_ns(), "unqualified", 0, "unqualified"
        )
        self.detector = Mock()

    def run_worker(self, provider="coreml", loader=None):
        before = set(threading.enumerate())
        with (
            patch.object(pipeline, "own_descendants"),
            patch(
                "aethron.vision.yolox.RGBDetector", return_value=self.detector, side_effect=loader
            ),
            patch("aethron_edge.sources.file.FileSource", return_value=self.source),
        ):
            pipeline._worker(
                Profile(name="cancel", driver="file", address="unused", provider=provider),
                self.channel,
                self.stop,
                SimpleNamespace(value=0),
                None,
                SimpleNamespace(value=0),
            )
        if self.source.open.called:
            self.source.close.assert_called_once()
        else:
            self.source.close.assert_not_called()
        self.assertEqual(set(threading.enumerate()), before)
        messages = []
        while not self.channel.empty():
            messages.append(self.channel.get_nowait())
        self.assertTrue(all(message["data"] is None for message in messages))
        return messages

    def test_stop_reaches_model_loading_and_prevents_capture(self):
        failures = []

        def load(*args, cancellation=None, **kwargs):
            if type(cancellation) is not InferenceCancellation:
                failures.append("missing load cancellation")
                self.stop.set()
                return self.detector
            self.stop.set()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                cancellation._check()
                time.sleep(0.001)
            failures.append("stop never reached load token")
            return self.detector

        messages = self.run_worker(loader=load)
        self.assertEqual(failures, [])
        self.assertEqual(messages, [{"data": None, "reason": "model_error", "latency_ms": 0}])
        self.source.open.assert_not_called()
        self.detector.infer.assert_not_called()

    def test_stop_after_load_success_never_opens_capture(self):
        def load(*args, **kwargs):
            self.stop.set()
            return self.detector

        self.assertEqual(self.run_worker(loader=load), [])
        self.source.open.assert_not_called()
        self.detector.infer.assert_not_called()

    def test_load_failure_closes_watcher_and_emits_fixed_fault(self):
        self.assertEqual(
            self.run_worker(loader=RuntimeError("private load details")),
            [{"data": None, "reason": "model_error", "latency_ms": 0}],
        )
        self.source.open.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec("onnxruntime"), "optional ORT provider required")
    def test_stop_terminates_active_call_with_fresh_options_per_frame(self):
        options_seen = []
        failures = []

        def infer(pixels, *, lighting, cancellation=None):
            if type(cancellation) is not InferenceCancellation:
                failures.append("missing cancellation token")
                self.stop.set()
                return []
            with cancellation._call() as options:
                options_seen.append(options)
                if len(options_seen) == 2:
                    self.stop.set()
                    deadline = time.monotonic() + 2
                    while not options.terminate and time.monotonic() < deadline:
                        time.sleep(0.001)
                    if not options.terminate:
                        failures.append("stop never reached native options")
                return []

        self.detector.infer.side_effect = infer
        messages = self.run_worker()
        self.assertEqual(failures, [])
        self.assertEqual(len(options_seen), 2)
        self.assertIsNot(options_seen[0], options_seen[1])
        self.assertFalse(options_seen[0].terminate)
        self.assertTrue(options_seen[1].terminate)
        self.assertEqual([m["reason"] for m in messages], ["clock_untrusted", "model_error"])
        self.assertEqual(messages[0]["inference_count"], 1)

    def test_stop_during_capture_never_submits_pixels(self):
        def read(deadline):
            self.stop.set()
            return self.source.read.return_value

        self.source.read.side_effect = read
        self.run_worker()
        self.detector.infer.assert_not_called()

    def test_stop_with_late_success_never_publishes_result(self):
        def infer(*args, **kwargs):
            self.stop.set()
            return [object()]

        self.detector.infer.side_effect = infer
        messages = self.run_worker()
        self.assertFalse(any("proposal_count" in m for m in messages))
        self.detector.infer.assert_called_once()

    def test_provider_failure_is_sanitized_and_closes_watcher(self):
        self.detector.infer.side_effect = RuntimeError("private native details")
        self.assertEqual(
            self.run_worker(), [{"data": None, "reason": "model_error", "latency_ms": 0}]
        )
        self.detector.infer.assert_called_once()

    def test_opencv_keeps_non_cancellable_call_and_unknown_output(self):
        self.source.read.side_effect = [self.source.read.return_value, SourceFault("source_lost")]
        self.detector.infer.return_value = []
        messages = self.run_worker("opencv")
        self.assertEqual([m["reason"] for m in messages], ["clock_untrusted", "source_lost"])
        self.assertNotIn("cancellation", self.detector.infer.call_args.kwargs)
