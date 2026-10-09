"""Native read-failure policy: live loss invalidates the slot; file EOF drains it."""

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron_edge.sources.base import MAX_RAW, CaptureSource, SourceConfig, SourceFault, _decode


class DecoderDisconnect(unittest.TestCase):
    def exercise(self, driver):
        import cv2
        import numpy as np

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "one-frame.avi"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 20, (64, 48))
            self.assertTrue(writer.isOpened())
            try:
                writer.write(np.full((48, 64, 3), 120, dtype=np.uint8))
            finally:
                writer.release()
            source = CaptureSource()
            source.driver = driver
            source.slot = bytearray(MAX_RAW)
            source.metadata = [0, 0, 0, 0]
            source.lock = threading.Lock()
            source.config = SourceConfig(driver, str(path), "ffmpeg", "fixture")
            stop = threading.Event()
            # A finite local clip supplies a real native read(False). This tests
            # the live loss policy without claiming RTSP transport qualification.
            worker = threading.Thread(
                target=_decode,
                args=(source.config, source.slot, source.metadata, source.lock, stop),
            )
            with patch("os.dup2"), patch.dict(os.environ):
                worker.start()
                try:
                    if driver == "rtsp":
                        worker.join(timeout=1)
                        self.assertFalse(worker.is_alive(), "live loss waited for an absent reader")
                        self.assertEqual(
                            source.read(time.monotonic_ns() + 100_000_000),
                            SourceFault("source_lost"),
                        )
                    else:
                        deadline = time.monotonic() + 1
                        while time.monotonic() < deadline:
                            with source.lock:
                                if source.metadata[0] != 0:
                                    break
                            time.sleep(0.005)
                        frame = source.read(time.monotonic_ns() + 100_000_000)
                        self.assertEqual(frame.pixels, bytes([120]) * (64 * 48 * 3))
                        self.assertEqual(frame.evidence, "recorded")
                        worker.join(timeout=1)
                        self.assertFalse(worker.is_alive())
                        self.assertEqual(
                            source.read(time.monotonic_ns() + 100_000_000),
                            SourceFault("source_lost"),
                        )
                finally:
                    stop.set()
                    worker.join(timeout=2)
                    self.assertFalse(worker.is_alive(), "decoder cleanup failed")

    def test_live_read_failure_discards_unread_frame_without_waiting_for_consumer(self):
        self.exercise("rtsp")

    def test_recorded_eof_preserves_final_frame_then_reports_loss(self):
        self.exercise("file")
