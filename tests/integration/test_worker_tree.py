"""A forced inference crash must not leave its own acquisition child running."""

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aethron_edge.config import Profile
from aethron_edge.pipeline import RuntimePipeline


def tree_worker(profile, channel, stop, group, decoder_lock, descendant):
    from aethron_edge.process_tree import own_descendants

    own_descendants(group)
    code = "import pathlib,sys,time\np=pathlib.Path(sys.argv[1])\nwhile True:\n p.write_text('alive')\n time.sleep(.02)"
    child = subprocess.Popen([sys.executable, "-c", code, profile.address])
    descendant.value = child.pid
    try:
        while not stop.wait(0.01):
            pass
    finally:
        child.terminate()
        child.wait(timeout=2)


class WorkerTree(unittest.TestCase):
    @unittest.skipUnless(os.name == "posix", "requires POSIX descendant signals")
    def test_denied_descendant_cleanup_still_stops_worker_and_retains_retry(self):
        for needs_kill in (False, True):
            with self.subTest(needs_kill=needs_kill):
                runtime = RuntimePipeline(Profile(name="tree", driver="replay", address="unused"))
                process = Mock(pid=12345)
                process.is_alive.side_effect = [True, needs_kill]
                runtime.process = process
                runtime.stop = Mock()
                runtime.group = SimpleNamespace(value=process.pid)
                runtime.descendant = SimpleNamespace(value=12346)
                runtime.last_result = {"state": "PRESENT"}
                runtime.sensor_state = "processing"
                runtime.sensor_expires_ns = 123
                with (
                    patch(
                        "aethron_edge.pipeline.os.killpg",
                        side_effect=PermissionError("private group"),
                    ),
                    patch(
                        "aethron_edge.pipeline.os.kill",
                        side_effect=PermissionError("private child"),
                    ) as kill,
                ):
                    with self.assertRaisesRegex(RuntimeError, "^worker_cleanup_failed$"):
                        runtime.stop_worker()
                    kill.assert_called_once_with(12346, signal.SIGKILL)
                process.terminate.assert_called_once()
                self.assertEqual(process.kill.call_count, int(needs_kill))
                self.assertEqual(process.join.call_count, 2 + int(needs_kill))
                process.close.assert_not_called()
                self.assertIs(runtime.process, process)
                self.assertEqual(runtime.descendant.value, 12346)
                self.assertIsNone(runtime.last_result)
                self.assertEqual(runtime.sensor_expires_ns, 0)

                # A later authorized cleanup attempt must still own the handles.
                process.is_alive.side_effect = None
                process.is_alive.return_value = False
                with (
                    patch("aethron_edge.pipeline.os.killpg", side_effect=ProcessLookupError()),
                    patch(
                        "aethron_edge.pipeline.os.kill", side_effect=ProcessLookupError()
                    ) as kill,
                ):
                    runtime.close()
                    runtime.close()
                    kill.assert_called_once_with(12346, signal.SIGKILL)
                process.close.assert_called_once()
                self.assertIsNone(runtime.process)
                self.assertEqual(runtime.descendant.value, 0)

    def test_forced_worker_death_reaps_its_own_descendants(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "heartbeat"
            runtime = RuntimePipeline(
                Profile(name="tree", driver="replay", address=str(marker)), worker=tree_worker
            )
            runtime.start()
            try:
                deadline = time.monotonic() + 15
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(marker.exists())
                runtime.process.kill()
                runtime.process.join(timeout=2)
                runtime.stop_worker()
                time.sleep(0.1)
                last = marker.stat().st_mtime_ns
                time.sleep(0.2)
                self.assertEqual(marker.stat().st_mtime_ns, last)
            finally:
                runtime.close()
