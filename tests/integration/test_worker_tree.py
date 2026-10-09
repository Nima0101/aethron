"""A forced inference crash must not leave its own acquisition child running."""

import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

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
