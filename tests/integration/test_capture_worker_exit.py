"""A dead live decoder cannot lend its unread slot fresh provenance."""

import time
import unittest

from aethron_edge.sources.base import SourceConfig, SourceFault
from aethron_edge.sources.file import FileSource
from aethron_edge.sources.rtsp import RTSPSource


def publish_until_killed(config, slot, metadata, lock, stop):
    with lock:
        slot[:12] = bytes([120]) * 12
        metadata[:] = [1, 2, 2, time.monotonic_ns()]
    stop.wait(10)


class CaptureWorkerExit(unittest.TestCase):
    def test_dead_live_worker_invalidates_unread_frame(self):
        source = RTSPSource(decoder=publish_until_killed)
        try:
            info = source.open(SourceConfig("rtsp", "rtsp://127.0.0.1/unused", "ffmpeg", "test"))
            self.assertEqual((info.width, info.height), (2, 2))
            source.process.terminate()
            source.process.join(timeout=2)
            self.assertFalse(source.alive)
            self.assertEqual(
                source.read(time.monotonic_ns() + 100_000_000), SourceFault("source_lost")
            )
        finally:
            source.close()

    def test_recorded_worker_exit_keeps_final_owned_frame(self):
        source = FileSource(decoder=publish_until_killed)
        try:
            source.open(SourceConfig("file", "unused", "ffmpeg", "test"))
            source.process.terminate()
            source.process.join(timeout=2)
            frame = source.read(time.monotonic_ns() + 100_000_000)
            self.assertEqual(frame.pixels, bytes([120]) * 12)
            self.assertEqual(frame.evidence, "recorded")
            self.assertEqual(
                source.read(time.monotonic_ns() + 100_000_000), SourceFault("source_lost")
            )
        finally:
            source.close()
