"""Recovery scheduling failure must leave the shared watchdog usable."""

import json
import tempfile
import threading
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aethron_edge.config import Profile
from aethron_edge.pipeline import RuntimePipeline
from aethron_edge.runtime.supervisor import ApplianceSupervisor

ROOT = Path(__file__).resolve().parents[2]


class RecoveryScheduling(unittest.TestCase):
    def make_runtime(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(
            patch("aethron_edge.pipeline.time.monotonic_ns", return_value=1_000_000_000)
        )
        runtime = ApplianceSupervisor()
        runtime.config = SimpleNamespace(
            runtime_mode="appliance", status_file=str(Path(directory) / "status.json")
        )
        failed = RuntimePipeline(Profile(name="failed", driver="replay", address="unused"))
        healthy = RuntimePipeline(Profile(name="healthy", driver="replay", address="unused"))
        failed.tick = Mock()
        healthy.tick = Mock()
        failed.process = Mock(pid=12345, is_alive=Mock(return_value=False))
        failed.stop = Mock()
        failed.group = SimpleNamespace(value=0)
        frame = json.loads((ROOT / "examples/temporal-blackout.jsonl").read_bytes().splitlines()[0])
        delta = 1001 - frame["at_ms"]
        frame["at_ms"] += delta
        for sensor in frame["sensors"]:
            sensor["at_ms"] += delta
            sensor["calibration_until_ms"] += delta
        self.now_ns = frame["at_ms"] * 1_000_000
        failed.last_result = failed.core.step(json.dumps(frame).encode(), now_ms=frame["at_ms"])
        self.assertEqual(failed.last_result["state"], "PRESENT")
        self.assertTrue(failed.last_result["tracks"])
        runtime.pipelines = {"failed": failed, "healthy": healthy}
        runtime.restarts = {name: deque(maxlen=5) for name in runtime.pipelines}
        runtime.next_restart = dict.fromkeys(runtime.pipelines, 0)
        return runtime, failed, healthy

    def check_failure(self, boundary, *, exhausted=False):
        runtime, failed, healthy = self.make_runtime()
        process = failed.process
        if exhausted:
            runtime.restarts["failed"].extend([self.now_ns] * 5)
        target = (
            "aethron_edge.runtime.supervisor.threading.Thread"
            if boundary == "construct"
            else "aethron_edge.runtime.supervisor.threading.Thread.start"
        )
        try:
            with (
                patch(
                    target, side_effect=RuntimeError("private scheduling diagnostic")
                ) as schedule,
                patch.object(failed, "stop_worker", wraps=failed.stop_worker) as stop,
            ):
                for now in (self.now_ns, self.now_ns + 3_000_000_000):
                    status = runtime.tick(now)
                    self.assertEqual(status["state"], "fault")
                    self.assertEqual(status["fault_count"], 1)
                schedule.assert_called_once()
                stop.assert_not_called()  # No blocking cleanup on the watchdog.
            self.assertEqual(healthy.tick.call_count, 2)
            self.assertEqual(failed.tick.call_count, 1)
            self.assertEqual(runtime.faults, {"failed"})
            self.assertEqual(runtime.recovering, set())
            self.assertEqual(runtime.maintenance, [])
            self.assertIs(failed.process, process)
            process.join.assert_not_called()
            scene = failed.snapshot(self.now_ns)
            self.assertEqual(scene["state"], "UNKNOWN")
            self.assertEqual(scene["tracks"], [])
            self.assertIsNone(scene["evidence"])
            self.assertNotIn(
                "private scheduling diagnostic", Path(runtime.config.status_file).read_text()
            )
        finally:
            runtime.shutdown()
        self.assertIsNone(failed.process)
        process.close.assert_called_once()

    def test_thread_construction_failure_latches_fault_and_preserves_watchdog(self):
        self.check_failure("construct")

    def test_thread_start_failure_latches_fault_without_unjoinable_task(self):
        self.check_failure("start")

    def test_exhausted_recovery_budget_still_contains_scheduling_failure(self):
        self.check_failure("start", exhausted=True)

    def test_successful_scheduling_retains_joinable_task(self):
        runtime, failed, healthy = self.make_runtime()
        # Exercise real thread start/join without creating an inference worker.
        runtime.stop.set()
        try:
            runtime.tick(self.now_ns)
            self.assertEqual(len(runtime.maintenance), 1)
            task = runtime.maintenance[0]
            self.assertIsInstance(task, threading.Thread)
            task.join(timeout=2)
            self.assertFalse(task.is_alive())
            self.assertEqual(runtime.recovering, set())
            self.assertEqual(runtime.faults, set())
            self.assertIsNone(failed.process)
            healthy.tick.assert_called_once_with(self.now_ns)
        finally:
            runtime.shutdown()

    def exercise_started_failure(self, *, shutdown):
        runtime, failed, healthy = self.make_runtime()
        entered, release = threading.Event(), threading.Event()
        tasks, errors = [], []
        start_thread = threading.Thread.start
        replacement = RuntimePipeline(failed.profile)

        def slow_start():
            entered.set()
            if not release.wait(5):
                raise TimeoutError("test did not release startup")

        def start_then_fail(task):
            tasks.append(task)
            start_thread(task)
            self.assertTrue(entered.wait(2))
            raise RuntimeError("private scheduling diagnostic")

        with (
            patch("aethron_edge.runtime.supervisor.RuntimePipeline", return_value=replacement),
            patch.object(replacement, "start", side_effect=slow_start),
            patch.object(replacement, "close", wraps=replacement.close) as close,
            patch.object(threading.Thread, "start", start_then_fail),
            patch("threading.excepthook", side_effect=lambda args: errors.append(args.exc_type)),
        ):
            try:
                status = runtime.tick(self.now_ns)
                self.assertEqual(status["state"], "fault")
                healthy.tick.assert_called_once_with(self.now_ns)
                task = tasks[0]
                if shutdown:
                    # The actual thread still owns startup. Expire its join
                    # budget without sleeping through the production timeout.
                    with patch.object(task, "join", return_value=None) as join:
                        with self.assertRaisesRegex(RuntimeError, "^appliance_cleanup_failed$"):
                            runtime.shutdown()
                    join.assert_called_once_with(timeout=4)
                    self.assertTrue(task.is_alive())
                    self.assertEqual(runtime.maintenance, [task])
                    self.assertIn("failed", runtime.recovering)
                release.set()
                task.join(timeout=2)
                self.assertFalse(task.is_alive())
                self.assertEqual(errors, [])
                # Even without shutdown, a scheduling fault must prevent this
                # late replacement from becoming the public scene owner.
                self.assertIs(runtime.pipelines["failed"], failed)
                close.assert_called_once_with()
                self.assertEqual(runtime.recovering, set())
                self.assertIn("failed", runtime.faults)
                scene = runtime.snapshot("failed")
                self.assertEqual(scene["state"], "UNKNOWN")
                self.assertEqual(scene["tracks"], [])
                self.assertNotIn(
                    "private scheduling diagnostic", Path(runtime.config.status_file).read_text()
                )
            finally:
                release.set()
                for task in tasks:
                    task.join(timeout=2)
                runtime.shutdown()
                replacement.close()

    def test_started_recovery_failure_remains_owned_by_shutdown(self):
        self.exercise_started_failure(shutdown=True)

    def test_started_recovery_failure_retires_unpublished_replacement(self):
        self.exercise_started_failure(shutdown=False)
