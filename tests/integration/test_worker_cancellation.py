"""Cooperative stop must reach active ORT calls and withdraw late results."""

import importlib.util
import json
import multiprocessing as mp
import os
import queue
import subprocess
import sys
import textwrap
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

    def test_watcher_cancellation_failure_rejects_late_success_and_reuse(self):
        attempted = threading.Event()

        def fail_cancel(token):
            attempted.set()
            raise RuntimeError("private native cancellation details")

        def late_success(*, cancellation):
            self.stop.set()
            self.assertTrue(attempted.wait(2), "watcher did not request cancellation")
            return object()

        with (
            patch.object(InferenceCancellation, "cancel", fail_cancel),
            patch.object(threading, "excepthook") as uncaught,
        ):
            watcher = pipeline._InferenceStop(self.stop)
            try:
                with self.assertRaisesRegex(RuntimeError, "^model_error$"):
                    watcher.call(late_success)
                operation = Mock()
                with self.assertRaisesRegex(RuntimeError, "^model_error$"):
                    watcher.call(operation)
                operation.assert_not_called()
            finally:
                watcher.close()
            uncaught.assert_not_called()
            self.assertIsNone(watcher.active)
            self.assertFalse(watcher.thread.is_alive())

    @unittest.skipUnless(importlib.util.find_spec("onnxruntime"), "optional ORT provider required")
    def test_native_cancellation_setter_failures_stay_inside_worker_boundary(self):
        for loading in (True, False):
            with self.subTest(loading=loading):
                self._native_cancellation_setter_failure(loading)

    def _native_cancellation_setter_failure(self, loading):
        self.setUp()
        attempted = threading.Event()

        class BrokenOptions:
            def set_load_cancellation_flag(options, value):
                attempted.set()
                raise RuntimeError("private native load cancellation details")

            @property
            def terminate(options):
                return False

            @terminate.setter
            def terminate(options, value):
                attempted.set()
                raise RuntimeError("private native run cancellation details")

        def operation(*args, cancellation=None, **kwargs):
            with cancellation._call(load=loading):
                self.stop.set()
                self.assertTrue(attempted.wait(2), "native cancellation not requested")
                return self.detector if loading else [object()]

        with (
            patch(
                "onnxruntime.SessionOptions" if loading else "onnxruntime.RunOptions",
                BrokenOptions,
            ),
            patch.object(threading, "excepthook") as uncaught,
        ):
            if not loading:
                self.detector.infer.side_effect = operation
            messages = self.run_worker(loader=operation if loading else None)
            uncaught.assert_not_called()
        self.assertEqual(messages, [{"data": None, "reason": "model_error", "latency_ms": 0}])
        if loading:
            self.source.open.assert_not_called()
            self.detector.infer.assert_not_called()
        else:
            self.detector.infer.assert_called_once()

    def test_isolation_failure_stops_before_dispatch_and_sanitizes_fault(self):
        class UnreadProfile:
            def __init__(self):
                self.accessed = []

            @property
            def driver(self):
                self.accessed.append("driver")
                raise AssertionError("dispatch must not begin")

        for error in (OSError("private isolation details"), RuntimeError("private platform")):
            for busy in (False, True):
                with self.subTest(error=type(error), busy=busy):
                    profile = UnreadProfile()
                    channel = queue.Queue(maxsize=1)
                    retained = {"data": None, "reason": "source_lost", "latency_ms": 0}
                    if busy:
                        channel.put_nowait(retained)
                    group, descendant = SimpleNamespace(value=0), SimpleNamespace(value=0)
                    with patch.object(pipeline, "own_descendants", side_effect=error) as own:
                        pipeline._worker(profile, channel, self.stop, group, None, descendant)
                    own.assert_called_once_with(group)
                    self.assertEqual(profile.accessed, [])
                    self.assertEqual((group.value, descendant.value), (0, 0))
                    self.assertEqual(
                        channel.get_nowait(),
                        retained
                        if busy
                        else {"data": None, "reason": "model_error", "latency_ms": 0},
                    )
                    self.assertTrue(channel.empty())

    @unittest.skipUnless(os.name == "posix", "requires POSIX session creation")
    def test_real_session_setup_failure_has_no_process_traceback(self):
        # A session leader cannot call setsid again. Exercise the actual OS
        # rejection in a separate process without changing the test runner.
        code = textwrap.dedent("""
            import json, os, queue, threading
            from types import SimpleNamespace
            from aethron_edge.pipeline import _worker
            assert os.getsid(0) == os.getpid()
            channel = queue.Queue()
            group, descendant = SimpleNamespace(value=0), SimpleNamespace(value=0)
            _worker(SimpleNamespace(driver='replay', address='unused'), channel,
                    threading.Event(), group, None, descendant)
            assert group.value == descendant.value == 0
            message = channel.get_nowait()
            assert channel.empty()
            print(json.dumps(message))
        """)
        result = subprocess.run(
            [sys.executable, "-c", code],
            start_new_session=True,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            json.loads(result.stdout), {"data": None, "reason": "model_error", "latency_ms": 0}
        )

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

    def test_source_cleanup_failure_publishes_only_fixed_fault(self):
        self.source.read.return_value = SourceFault("source_lost")
        self.source.close.side_effect = RuntimeError("private source cleanup details")
        messages = self.run_worker("opencv")
        self.assertEqual([m["reason"] for m in messages], ["source_lost", "model_error"])
        self.assertEqual(messages[-1], {"data": None, "reason": "model_error", "latency_ms": 0})
        self.detector.infer.assert_not_called()

    def test_watcher_cleanup_failure_still_closes_source(self):
        self.source.read.return_value = SourceFault("source_lost")
        close = pipeline._InferenceStop.close

        def fail_after_join(watcher):
            close(watcher)
            raise RuntimeError("private watcher cleanup details")

        with patch.object(pipeline._InferenceStop, "close", fail_after_join):
            messages = self.run_worker()
        self.source.close.assert_called_once()
        self.assertEqual([m["reason"] for m in messages], ["source_lost", "model_error"])
        self.assertEqual(messages[-1], {"data": None, "reason": "model_error", "latency_ms": 0})

    def test_execution_and_both_cleanup_failures_remain_fixed_faults(self):
        self.detector.infer.side_effect = RuntimeError("private inference details")
        self.source.close.side_effect = RuntimeError("private source cleanup details")
        close = pipeline._InferenceStop.close

        def fail_after_join(watcher):
            close(watcher)
            raise RuntimeError("private watcher cleanup details")

        with patch.object(pipeline._InferenceStop, "close", fail_after_join):
            messages = self.run_worker()
        self.detector.infer.assert_called_once()
        self.source.close.assert_called_once()
        self.assertEqual(messages, [{"data": None, "reason": "model_error", "latency_ms": 0}] * 2)
