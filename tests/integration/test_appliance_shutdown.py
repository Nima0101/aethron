"""One cleanup failure must not abandon the appliance's other resources."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aethron_edge.config import Profile
from aethron_edge.pipeline import RuntimePipeline
from aethron_edge.runtime.supervisor import ApplianceSupervisor

ROOT = Path(__file__).resolve().parents[2]


class ApplianceShutdown(unittest.TestCase):
    def setUp(self):
        self.make_runtime()

    def make_runtime(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(
            patch("aethron_edge.pipeline.time.monotonic_ns", return_value=1_000_000_000)
        )
        self.runtime = ApplianceSupervisor()
        self.runtime.config = SimpleNamespace(
            runtime_mode="appliance", status_file=str(Path(directory) / "status.json")
        )
        self.runtime.thread = Mock(is_alive=Mock(return_value=False))
        self.runtime.maintenance = [Mock(is_alive=Mock(return_value=False)) for _ in range(2)]
        self.runtime.telemetry = {
            name: Mock(snapshot=Mock(return_value={"state": "stopped"}))
            for name in ("first", "second")
        }
        self.processes = []
        for name in ("first", "second"):
            pipeline = RuntimePipeline(Profile(name=name, driver="replay", address="unused"))
            process = Mock(pid=12345, is_alive=Mock(return_value=False))
            pipeline.process = process
            pipeline.stop = Mock()
            pipeline.group = SimpleNamespace(value=0)
            frame = json.loads(
                (ROOT / "examples/temporal-blackout.jsonl").read_bytes().splitlines()[0]
            )
            delta = 1001 - frame["at_ms"]
            frame["at_ms"] += delta
            for sensor in frame["sensors"]:
                sensor["at_ms"] += delta
                sensor["calibration_until_ms"] += delta
            pipeline.last_result = pipeline.core.step(json.dumps(frame).encode(), now_ms=1001)
            self.assertEqual(pipeline.last_result["state"], "PRESENT")
            self.assertTrue(pipeline.last_result["tracks"])
            self.runtime.pipelines[name] = pipeline
            self.processes.append(process)

    def failpoints(self):
        return [
            self.runtime.thread.join,
            self.runtime.maintenance[0].join,
            self.runtime.telemetry["first"].close,
            self.processes[0].join,
        ]

    def assert_cleanup_attempts(self):
        self.runtime.thread.join.assert_called_with(timeout=2)
        for task in self.runtime.maintenance:
            task.join.assert_called_with(timeout=4)
        for source in self.runtime.telemetry.values():
            source.close.assert_called()
        for pipeline in self.runtime.pipelines.values():
            pipeline.stop.set.assert_called()
            result = pipeline.snapshot(1_001_000_000)
            self.assertEqual(result["state"], "UNKNOWN")
            self.assertEqual(result["tracks"], [])
            self.assertIsNone(result["evidence"])
        self.assertIsNone(self.runtime.pipelines["second"].process)
        self.processes[1].close.assert_called_once()

    def assert_failed_shutdown(self):
        with self.assertRaises(Exception) as caught:
            self.runtime.shutdown()
        self.assertTrue(self.runtime.stop.is_set())
        self.assert_cleanup_attempts()
        self.assertIs(type(caught.exception), RuntimeError)
        self.assertEqual(str(caught.exception), "appliance_cleanup_failed")
        status = Path(self.runtime.config.status_file).read_text()
        self.assertNotIn("private diagnostic", status)
        self.assertEqual(json.loads(status)["state"], "fault")
        self.assertGreaterEqual(json.loads(status)["fault_count"], 1)

    def test_each_cleanup_failure_still_retires_other_resources(self):
        # Fresh fixture for each boundary so an earlier successful cleanup
        # cannot conceal an omitted close in a later case.
        for index in range(4):
            with self.subTest(boundary=index):
                if index:
                    self.make_runtime()
                failing = self.failpoints()[index]
                failing.side_effect = OSError("private diagnostic")
                self.assert_failed_shutdown()

    def test_simultaneous_failures_preserve_retry_ownership(self):
        for failing in self.failpoints():
            failing.side_effect = OSError("private diagnostic")
        self.assert_failed_shutdown()
        self.assertIs(self.runtime.pipelines["first"].process, self.processes[0])
        self.processes[0].close.assert_not_called()
        for failing in self.failpoints():
            failing.side_effect = None
        self.runtime.shutdown()
        self.assert_cleanup_attempts()
        self.assertIsNone(self.runtime.pipelines["first"].process)
        self.processes[0].close.assert_called_once()
        status = json.loads(Path(self.runtime.config.status_file).read_text())
        self.assertEqual(status["state"], "stopped")

    def test_successful_shutdown_and_repeated_shutdown(self):
        self.runtime.shutdown()
        self.runtime.shutdown()
        self.assert_cleanup_attempts()
        self.processes[0].close.assert_called_once()
        status = json.loads(Path(self.runtime.config.status_file).read_text())
        self.assertEqual(status["state"], "stopped")
        self.assertEqual(status["fault_count"], 0)

    def test_incomplete_joins_report_fault_and_retain_cleanup_ownership(self):
        for index in range(3):
            with self.subTest(thread=index):
                if index:
                    self.make_runtime()
                tasks = [self.runtime.thread, *self.runtime.maintenance]
                pending = tasks[index]
                pending.is_alive.return_value = True
                self.assert_failed_shutdown()
                self.assertEqual([self.runtime.thread, *self.runtime.maintenance], tasks)
                for task in tasks:
                    task.is_alive.assert_called_once_with()
                # Completion permits a later explicit shutdown to succeed.
                pending.is_alive.return_value = False
                self.runtime.shutdown()
                self.assert_cleanup_attempts()
                status = json.loads(Path(self.runtime.config.status_file).read_text())
                self.assertEqual(status["state"], "stopped")

    def test_join_liveness_error_is_private_and_does_not_skip_cleanup(self):
        self.runtime.maintenance[0].is_alive.side_effect = OSError("private diagnostic")
        self.assert_failed_shutdown()
        self.runtime.maintenance[1].is_alive.assert_called_once_with()

    def assert_reporting_failure(self):
        with self.assertRaises(Exception) as caught:
            self.runtime.shutdown()
        self.assert_cleanup_attempts()
        self.assertIs(type(caught.exception), RuntimeError)
        self.assertEqual(str(caught.exception), "appliance_cleanup_failed")
        self.assertIsNone(caught.exception.__context__)
        self.assertIn("shutdown_cleanup", self.runtime.faults)

    def test_status_collection_failure_is_private_after_cleanup(self):
        snapshot = self.runtime.telemetry["first"].snapshot
        snapshot.side_effect = ValueError("private diagnostic")
        self.assert_reporting_failure()
        snapshot.side_effect = None
        self.runtime.shutdown()
        status = json.loads(Path(self.runtime.config.status_file).read_text())
        self.assertEqual(status["state"], "stopped")

    def test_reporting_failure_does_not_replace_existing_cleanup_fault(self):
        self.processes[0].join.side_effect = OSError("private cleanup diagnostic")
        self.runtime.telemetry["first"].snapshot.side_effect = ValueError("private diagnostic")
        self.assert_reporting_failure()
        self.assertIs(self.runtime.pipelines["first"].process, self.processes[0])
        self.processes[0].close.assert_not_called()

    def test_status_publication_failures_are_not_successful_shutdowns(self):
        for error in (OSError, ValueError):
            with self.subTest(error=error.__name__):
                with patch(
                    "aethron_edge.runtime.supervisor.publish_status",
                    side_effect=error("private diagnostic"),
                ):
                    self.assert_reporting_failure()
                self.runtime.shutdown()
                status = json.loads(Path(self.runtime.config.status_file).read_text())
                self.assertEqual(status["state"], "stopped")
