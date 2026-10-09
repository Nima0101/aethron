import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron_edge.config import ApplianceConfig
from aethron_edge.runtime.supervisor import ApplianceSupervisor

ROOT = Path(__file__).resolve().parents[2]


class Lifecycle(unittest.TestCase):
    def test_slow_worker_cleanup_cannot_block_watchdog(self):
        with tempfile.TemporaryDirectory() as directory:
            config = ApplianceConfig.model_validate(
                {
                    "version": 1,
                    "status_file": str(Path(directory) / "status.json"),
                    "profiles": [
                        {
                            "name": "bench",
                            "driver": "replay",
                            "address": str(ROOT / "examples/temporal-blackout.jsonl"),
                        }
                    ],
                }
            )
            runtime = ApplianceSupervisor()
            runtime.boot(config)
            try:
                p = runtime.pipelines["bench"]
                runtime.stop.set()
                runtime.thread.join(timeout=1)
                runtime.last_status = time.monotonic_ns()
                p.last_message_ns = 0
                original_stop = p.stop_worker

                release = threading.Event()
                entered = threading.Event()
                returned = threading.Event()

                def slow_stop():
                    entered.set()
                    release.wait(10)
                    original_stop()

                def tick():
                    runtime.tick(time.monotonic_ns())
                    returned.set()

                with patch.object(p, "stop_worker", side_effect=slow_stop):
                    caller = threading.Thread(target=tick)
                    caller.start()
                    try:
                        self.assertTrue(entered.wait(5))
                        self.assertTrue(returned.wait(2), "watchdog waited for blocked cleanup")
                    finally:
                        release.set()
                        caller.join(timeout=5)
            finally:
                runtime.shutdown()

    def test_zero_viewers_processing_and_disk_full_fault(self):
        with tempfile.TemporaryDirectory() as directory:
            config = ApplianceConfig.model_validate(
                {
                    "version": 1,
                    "status_file": str(Path(directory) / "status.json"),
                    "profiles": [
                        {
                            "name": "bench",
                            "driver": "replay",
                            "address": str(ROOT / "examples/temporal-blackout.jsonl"),
                        }
                    ],
                }
            )
            runtime = ApplianceSupervisor()
            runtime.boot(config)
            try:
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and runtime.pipelines["bench"].processed < 3:
                    time.sleep(0.02)
                self.assertGreater(runtime.pipelines["bench"].processed, 2)
                with patch(
                    "aethron_edge.runtime.supervisor.publish_status",
                    side_effect=OSError("disk full"),
                ):
                    with runtime.lock:
                        runtime.last_status = 0
                        runtime.tick(time.monotonic_ns())
                self.assertIn("status_storage", runtime.faults)
                self.assertGreater(runtime.pipelines["bench"].processed, 2)
            finally:
                runtime.shutdown()

    def test_crash_recovery_budget_latches_without_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            config = ApplianceConfig.model_validate(
                {
                    "version": 1,
                    "status_file": str(Path(directory) / "status.json"),
                    "profiles": [
                        {
                            "name": "broken",
                            "driver": "replay",
                            "address": str(Path(directory) / "missing"),
                        }
                    ],
                }
            )
            runtime = ApplianceSupervisor()
            runtime.boot(config)
            try:
                deadline = time.monotonic() + 55
                while time.monotonic() < deadline and (
                    "broken" not in runtime.faults
                    or runtime.pipelines["broken"].process is not None
                ):
                    time.sleep(0.05)
                self.assertIn("broken", runtime.faults)
                self.assertEqual(len(runtime.restarts["broken"]), 5)
                self.assertIsNone(runtime.pipelines["broken"].process)
                self.assertEqual(runtime.snapshot("broken")["state"], "UNKNOWN")
            finally:
                runtime.shutdown()
