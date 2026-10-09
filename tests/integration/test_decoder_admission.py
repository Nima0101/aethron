import multiprocessing as mp
import time
import tracemalloc
import unittest

from aethron_edge.sources.base import MAX_RAW, SourceConfig, SourceFault
from aethron_edge.sources.file import FileSource


def malformed_decoder(config, slot, metadata, lock, stop):
    with lock:
        metadata[:] = [1, -1, 2, time.monotonic_ns()]
    stop.wait(10)


class UnreadablePixels:
    def __getitem__(self, key):
        raise AssertionError("invalid metadata touched pixel buffer")


class DecoderAdmission(unittest.TestCase):
    def setUp(self):
        ctx = mp.get_context("spawn")
        self.source = FileSource()
        self.source.slot = ctx.RawArray("B", MAX_RAW)
        self.source.metadata = ctx.RawArray("q", 4)
        self.source.lock = ctx.Lock()
        self.source.config = SourceConfig("file", "synthetic", "ffmpeg", "bench")

    def read(self, width, height, sequence=1):
        self.source.metadata[:] = [sequence, width, height, 1234]
        return self.source.read(time.monotonic_ns() + 5_000_000_000)

    def test_invalid_dimensions_fault_before_any_pixel_access(self):
        self.source.slot = UnreadablePixels()
        for width, height in (
            (0, 2),
            (-1, 2),
            (2, 0),
            (2, -1),
            (-1, -1),
            (1921, 2),
            (2, 1081),
            (2**63 - 1, 2**63 - 1),
        ):
            with self.subTest(width=width, height=height):
                fault = self.read(width, height)
                self.assertEqual(fault, SourceFault("source_lost"))
                self.assertEqual((self.source.last_sequence, self.source.drops), (0, 0))
                self.assertLess(self.source.metadata[0], 0)
                self.assertEqual(self.source.read(time.monotonic_ns() + 1_000_000_000), fault)

    def test_invalid_negotiation_never_advertises_dimensions(self):
        source = FileSource(decoder=malformed_decoder)
        try:
            info = source.open(SourceConfig("file", "synthetic", "ffmpeg", "bench"))
            self.assertEqual((info.width, info.height), (None, None))
            self.assertEqual(
                source.read(time.monotonic_ns() + 1_000_000_000), SourceFault("source_lost")
            )
        finally:
            source.close()
        self.assertFalse(source.alive)

    def test_snapshot_is_owned_exact_length_and_preserves_provenance(self):
        view = memoryview(self.source.slot).cast("B")
        view[:] = b"\xff" * MAX_RAW
        expected = bytes(range(12))
        view[:12] = expected
        frame = self.read(2, 2, sequence=3)
        self.assertEqual(frame.pixels, expected)
        view[:12] = b"\x00" * 12
        self.assertEqual(frame.pixels, expected)
        self.assertEqual(
            (frame.width, frame.height, frame.sequence, frame.receive_ns), (2, 2, 3, 1234)
        )
        self.assertEqual(
            (frame.clock_id, frame.capture_ns, frame.evidence), ("recorded_media", None, "recorded")
        )
        self.assertEqual(self.source.drops, 2)
        self.assertEqual(self.source.metadata[0], 0)

    def test_maximum_frame_avoids_per_byte_python_list(self):
        tracemalloc.start()
        try:
            frame = self.read(1920, 1080)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(len(frame.pixels), MAX_RAW)
        # Regression ceiling for temporary Python allocations, not a runtime/RSS budget.
        self.assertLess(peak, MAX_RAW * 3)

    def test_minimum_and_axis_bounds_remain_valid(self):
        for width, height in ((1, 1), (1920, 1), (1, 1080)):
            with self.subTest(width=width, height=height):
                frame = self.read(width, height)
                self.assertEqual(len(frame.pixels), width * height * 3)
