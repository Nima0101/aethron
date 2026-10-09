import unittest

from aethron_edge.calibration import CalibrationRecord
from aethron_edge.sources.base import FrameEnvelope, SourceFault
from aethron_edge.timebase import CaptureClock


class ClockBoundary(unittest.TestCase):
    def frame(self, **changes):
        values = {
            "pixels": b"\0" * 12,
            "width": 2,
            "height": 2,
            "sequence": 1,
            "capture_ns": 1_000_000_000,
            "receive_ns": 1_000_000_000,
            "clock_id": "host_monotonic",
            "clock_uncertainty_ns": 0,
            "calibration_id": "bench",
            "modality": "rgb",
            "evidence": "external_unverified",
        }
        return FrameEnvelope(**dict(values, **changes))

    def test_age_includes_uncertainty_and_does_not_use_receive_time(self):
        self.assertNotIsInstance(
            CaptureClock().map_capture(self.frame(), 1_100_000_000), SourceFault
        )
        for changes, now in [
            ({}, 1_101_000_000),
            ({"clock_uncertainty_ns": 1}, 1_100_000_000),
            ({"capture_ns": None}, 1_000_000_000),
            ({"capture_ns": 1_000_000_001}, 1_000_000_000),
        ]:
            self.assertIsInstance(
                CaptureClock().map_capture(self.frame(**changes), now), SourceFault
            )

    def test_boolean_capture_clock_is_not_an_integer_clock(self):
        self.assertIsInstance(
            CaptureClock().map_capture(self.frame(capture_ns=True, receive_ns=1), 1), SourceFault
        )

    def test_duplicate_and_clock_reset_withdraw_linkage(self):
        clock = CaptureClock()
        clock.map_capture(self.frame(), 1_000_000_000)
        self.assertIsInstance(clock.map_capture(self.frame(), 1_000_000_000), SourceFault)
        self.assertIsInstance(
            clock.map_capture(self.frame(sequence=2, clock_id="new"), 1_000_000_000), SourceFault
        )

    def test_calibration_resolution_remount_and_expiry(self):
        c = CalibrationRecord("bench", 2, 2, 2000, "mount-a", (1, 0, 0, 0, 1, 0, 0, 0, 1), 0.001)
        self.assertTrue(c.valid_for(self.frame(), 1500, "mount-a"))
        self.assertFalse(c.valid_for(self.frame(width=3), 1500, "mount-a"))
        self.assertFalse(c.valid_for(self.frame(), 1500, "mount-b"))
        self.assertFalse(c.valid_for(self.frame(), 2001, "mount-a"))

    def test_unapplied_or_nonfinite_transform_is_rejected(self):
        for transform in ((1, 0, 0.1, 0, 1, 0, 0, 0, 1), (float("nan"),) * 9):
            c = CalibrationRecord("bench", 2, 2, 2000, "mount-a", transform, 0.001)
            self.assertFalse(c.valid_for(self.frame(), 1500, "mount-a"))

    def test_skew_bounds_include_both_uncertainties(self):
        self.assertTrue(CaptureClock.compatible(0, 0, 50_000_000, 0))
        self.assertFalse(CaptureClock.compatible(0, 1, 50_000_000, 0))
        self.assertFalse(CaptureClock.compatible(0, 0, 51_000_000, 0))

    def test_skew_rejects_malformed_scalars_without_coercion(self):
        class IntegerSubclass(int):
            pass

        for value in (
            True,
            False,
            -1,
            0.0,
            0.5,
            float("nan"),
            float("inf"),
            float("-inf"),
            None,
            "0",
            IntegerSubclass(0),
        ):
            for index in range(4):
                with self.subTest(value=value, index=index):
                    args = [0, 0, 0, 0]
                    args[index] = value
                    self.assertIs(CaptureClock.compatible(*args), False)

    def test_skew_preserves_nanosecond_boundary_at_large_epochs(self):
        for base in (0, 2**53, 2**64 - 1, 2**128, 10**100):
            for delta in (-1, 0, 1):
                a, b = base, base + 40_000_000 + delta
                with self.subTest(base=base, delta=delta):
                    self.assertIs(CaptureClock.compatible(a, 4_000_000, b, 6_000_000), delta <= 0)
                    self.assertIs(CaptureClock.compatible(b, 6_000_000, a, 4_000_000), delta <= 0)
        for error in (2**64 - 1, 2**64, 2**128):
            self.assertFalse(CaptureClock.compatible(0, error, 0, error))
