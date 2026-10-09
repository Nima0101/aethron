import multiprocessing as mp
import threading
import time
import types
import unittest
from unittest.mock import patch

from aethron_edge.sources.base import MAX_RAW, SourceConfig, SourceFault, _decode
from aethron_edge.sources.file import FileSource


class DecoderPublication(unittest.TestCase):
    def publish(self, width, height, nbytes, raw):
        # Inject only the backend boundary; exercise the real publication and read paths.
        ctx = mp.get_context("spawn")
        source = FileSource()
        source.slot = ctx.RawArray("B", MAX_RAW)
        source.metadata = ctx.RawArray("q", 4)
        source.lock = ctx.Lock()
        source.config = SourceConfig("file", "synthetic", "ffmpeg", "bench")
        stop = threading.Event()
        pixels = types.SimpleNamespace(shape=(height, width, 3), nbytes=nbytes)

        class Capture:
            released = False

            def open(self, *args):
                return True

            def set(self, *args):
                return True

            def get(self, prop):
                return {1: width, 2: height, 3: 30}[prop]

            def read(self):
                stop.set()
                return True, pixels

            def release(self):
                self.released = True

        capture = Capture()
        backend = types.SimpleNamespace(
            CAP_FFMPEG=0,
            CAP_V4L2=1,
            CAP_AVFOUNDATION=2,
            CAP_MSMF=3,
            CAP_PROP_OPEN_TIMEOUT_MSEC=4,
            CAP_PROP_READ_TIMEOUT_MSEC=5,
            CAP_PROP_BUFFERSIZE=6,
            CAP_PROP_FRAME_WIDTH=1,
            CAP_PROP_FRAME_HEIGHT=2,
            CAP_PROP_FPS=3,
            COLOR_BGR2RGB=7,
            setNumThreads=lambda _: None,
            VideoCapture=lambda: capture,
            cvtColor=lambda *_: types.SimpleNamespace(tobytes=lambda: raw),
        )
        with patch.dict("sys.modules", {"cv2": backend}), patch("os.dup2"):
            _decode(source.config, source.slot, source.metadata, source.lock, stop)
        self.assertTrue(capture.released)
        return source.read(time.monotonic_ns() + 5_000_000_000)

    def test_non_rgb8_byte_counts_never_publish_a_frame(self):
        for nbytes, raw in ((48, bytes(48)), (11, bytes(11)), (12, bytes(11)), (12, bytes(13))):
            with self.subTest(nbytes=nbytes, raw_length=len(raw)):
                self.assertEqual(self.publish(2, 2, nbytes, raw), SourceFault("source_lost"))

    def test_full_and_small_frames_preserve_all_bytes_and_untrusted_clock(self):
        for width, height in ((2, 2), (1920, 1080)):
            size = width * height * 3
            raw = (bytes(range(256)) * ((size + 255) // 256))[:size]
            frame = self.publish(width, height, size, raw)
            self.assertEqual(frame.pixels, raw)
            self.assertEqual((frame.width, frame.height, frame.sequence), (width, height, 1))
            self.assertEqual((frame.capture_ns, frame.clock_id), (None, "recorded_media"))
            self.assertEqual(frame.evidence, "recorded")
