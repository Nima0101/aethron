import unittest

from aethron_edge.sources.base import FrameEnvelope, SourceFault
from aethron_edge.timebase import CaptureClock, MappedFrame


class CaptureClockState(unittest.TestCase):
    def sample(
        self, clock, sequence, stamp, *, now=1_000_000_000, error=0, clock_id="host_monotonic"
    ):
        frame = FrameEnvelope(b"\0" * 3, 1, 1, sequence, stamp, now, clock_id, error, "bench")
        return clock.map_capture(frame, now)

    def test_out_of_order_rejection_cannot_readmit_previous_sequence(self):
        clock = CaptureClock()
        self.assertIsInstance(self.sample(clock, 10, 1_000_000_000), MappedFrame)
        self.assertEqual(self.sample(clock, 9, 990_000_000), SourceFault("clock_untrusted"))
        self.assertEqual(self.sample(clock, 10, 1_000_000_000), SourceFault("clock_untrusted"))
        self.assertIsInstance(self.sample(clock, 11, 1_000_000_001, now=1_000_000_001), MappedFrame)

    def test_rejected_regression_cannot_readmit_older_capture_with_new_sequence(self):
        clock = CaptureClock()
        self.assertIsInstance(self.sample(clock, 10, 1_000_000_000), MappedFrame)
        self.assertEqual(self.sample(clock, 11, 980_000_000), SourceFault("clock_untrusted"))
        self.assertEqual(self.sample(clock, 12, 990_000_000), SourceFault("clock_untrusted"))
        self.assertIsInstance(self.sample(clock, 13, 1_000_000_001, now=1_000_000_001), MappedFrame)

    def test_future_rejection_keeps_conservative_high_water_until_time_catches_up(self):
        clock = CaptureClock()
        self.assertEqual(self.sample(clock, 10, 1_000_000_010), SourceFault("clock_untrusted"))
        self.assertEqual(self.sample(clock, 9, 999_999_999), SourceFault("clock_untrusted"))
        self.assertEqual(
            self.sample(clock, 11, 1_000_000_005, now=1_000_000_010), SourceFault("clock_untrusted")
        )
        self.assertIsInstance(self.sample(clock, 12, 1_000_000_011, now=1_000_000_011), MappedFrame)

    def test_clock_change_stays_untrusted_and_instances_have_independent_state(self):
        clock = CaptureClock()
        self.assertIsInstance(self.sample(clock, 1, 999_999_999), MappedFrame)
        self.assertEqual(
            self.sample(clock, 2, 1_000_000_000, clock_id="other"), SourceFault("clock_untrusted")
        )
        self.assertEqual(
            self.sample(clock, 3, 1_000_000_001, now=1_000_000_001), SourceFault("clock_untrusted")
        )
        self.assertIsInstance(self.sample(CaptureClock(), 1, 1_000_000_000), MappedFrame)
