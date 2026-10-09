import tempfile
import time
import unittest
from pathlib import Path

from aethron_edge.sources.base import SourceConfig, SourceFault
from aethron_edge.sources.file import FileSource
from aethron_edge.sources.rtsp import RTSPSource
from aethron_edge.sources.uvc import UVCSource


def virtual_uvc(config, slot, metadata, lock, stop):
    # A virtual capture backend exercises the same bounded host worker boundary.
    # It is explicitly not a claim about any physical UVC camera.
    with lock:
        slot[:12] = b"\x7f" * 12
        metadata[:] = [1, 2, 2, time.monotonic_ns()]
    stop.wait(10)


class Sources(unittest.TestCase):
    def test_virtual_uvc_capture_stall_deadline_and_cancellation(self):
        source = UVCSource(decoder=virtual_uvc)
        source.open(SourceConfig("uvc", "0", "v4l2", "virtual"))
        frame = source.read(time.monotonic_ns() + 5_000_000_000)
        self.assertNotIsInstance(frame, SourceFault)
        self.assertEqual(len(frame.pixels), 12)
        self.assertIsNone(frame.capture_ns)
        self.assertNotIn("pixels=", repr(frame))
        start = time.monotonic()
        self.assertIsInstance(source.read(time.monotonic_ns() + 50_000_000), SourceFault)
        self.assertLess(time.monotonic() - start, 0.5)
        source.close()
        self.assertFalse(source.alive)

    def test_file_real_decode_eof_close_reopen(self):
        import cv2
        import numpy as np

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.avi"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 20, (64, 48))
            writer.write(np.full((48, 64, 3), 120, dtype=np.uint8))
            writer.release()
            source = FileSource()
            cfg = SourceConfig(
                driver="file", address=str(path), backend="ffmpeg", calibration_id="test"
            )
            for _ in range(2):
                info = source.open(cfg)
                self.assertEqual(
                    (info.width, info.height, info.encoding),
                    (64, 48, "rgb8"),
                    {
                        "metadata": list(source.metadata),
                        "alive": source.alive,
                        "exitcode": source.process.exitcode,
                    },
                )
                frame = source.read(time.monotonic_ns() + 5_000_000_000)
                self.assertNotIsInstance(frame, SourceFault)
                self.assertEqual((frame.width, frame.height, len(frame.pixels)), (64, 48, 9216))
                self.assertEqual(frame.evidence, "recorded")
                self.assertEqual(frame.clock_id, "recorded_media")
                self.assertIsInstance(source.read(time.monotonic_ns() + 2_000_000_000), SourceFault)
                source.close()
            self.assertFalse(source.alive)

    def test_invalid_configs_do_not_open_any_device(self):
        for source, cfg in [
            (RTSPSource(), SourceConfig("rtsp", "https://example.invalid", "ffmpeg", "test")),
            (UVCSource(), SourceConfig("uvc", "-1", "v4l2", "test")),
            (FileSource(), SourceConfig("file", "missing", "automatic", "test")),
        ]:
            with self.assertRaises(ValueError):
                source.open(cfg)

    def test_corrupt_and_oversized_media_fail_without_fresh_frame(self):
        import cv2
        import numpy as np

        with tempfile.TemporaryDirectory() as directory:
            corrupt = Path(directory) / "corrupt.avi"
            corrupt.write_bytes(b"not an encoded frame")
            oversized = Path(directory) / "oversized.avi"
            writer = cv2.VideoWriter(
                str(oversized), cv2.VideoWriter_fourcc(*"MJPG"), 10, (1922, 1080)
            )
            self.assertTrue(writer.isOpened())
            writer.write(np.zeros((1080, 1922, 3), dtype=np.uint8))
            writer.release()
            for path in (corrupt, oversized):
                source = FileSource()
                try:
                    source.open(SourceConfig("file", str(path), "ffmpeg", "unqualified"))
                    self.assertIsInstance(
                        source.read(time.monotonic_ns() + 2_000_000_000), SourceFault
                    )
                finally:
                    source.close()

    def test_missing_file_fails_with_fixed_fault(self):
        source = FileSource()
        source.open(SourceConfig("file", "/nonexistent-private-sentinel", "ffmpeg", "test"))
        fault = source.read(time.monotonic_ns() + 5_000_000_000)
        self.assertIsInstance(fault, SourceFault)
        self.assertNotIn("private-sentinel", repr(fault))
        source.close()
