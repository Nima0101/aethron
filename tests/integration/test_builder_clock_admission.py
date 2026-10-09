import json
import unittest
from decimal import Decimal
from fractions import Fraction

from aethron_edge.calibration import CalibrationRecord
from aethron_edge.pipeline import build_v3
from aethron_edge.sources.base import FrameEnvelope
from aethron_edge.timebase import MappedFrame


class BuilderClockAdmission(unittest.TestCase):
    def build(self, exposure=1_000_000_000, uncertainty=0, now=1_000_000_000):
        frame = FrameEnvelope(
            b"\0" * 12, 2, 2, 1, exposure, exposure, "host_monotonic", uncertainty, "bench"
        )
        calibration = CalibrationRecord(
            "bench", 2, 2, 2**100, "fixed", (1, 0, 0, 0, 1, 0, 0, 0, 1), 0.001
        )
        return build_v3(MappedFrame(frame, exposure, uncertainty), [], calibration, now_ns=now)

    def test_malformed_clock_values_reject_before_arithmetic(self):
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
            None,
            "0",
            Decimal(0),
            Fraction(0),
            IntegerSubclass(0),
        ):
            for field in ("exposure", "uncertainty", "now"):
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, "^clock_untrusted$"):
                        self.build(**{field: value})

    def test_noninteger_cannot_run_conversion_hooks(self):
        class ArithmeticTrap:
            def __floordiv__(self, other):
                raise AssertionError("untrusted clock arithmetic executed")

            __sub__ = __rsub__ = __floordiv__

        for field in ("exposure", "uncertainty", "now"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "^clock_untrusted$"):
                    self.build(**{field: ArithmeticTrap()})

    def test_conservative_rounding_and_age_boundary_are_unchanged(self):
        for exposure, uncertainty, now, expected in (
            (0, 0, 0, 0),
            (1_000_000_000, 0, 1_100_000_000, 1000),
            (1_000_000_001, 1, 1_100_000_000, 1000),
            (1_000_000_000, 1, 1_000_000_000, 999),
            (9_007_199_254_740_993, 1, 9_007_199_254_740_993, 9_007_199_254),
        ):
            with self.subTest(exposure=exposure, uncertainty=uncertainty, now=now):
                payload = json.loads(self.build(exposure, uncertainty, now))
                self.assertEqual(payload["at_ms"], expected)
                self.assertIs(type(payload["at_ms"]), int)
                self.assertEqual(payload["sensors"][0]["at_ms"], expected)
                self.assertTrue(payload["sensors"][0]["registered"])
        for exposure, uncertainty, now in (
            (1_000_000_000, 1, 1_100_000_000),
            (1_000_000_000, 0, 1_101_000_000),
            (1_001_000_000, 0, 1_000_000_000),
            (0, 1, 0),
        ):
            with self.subTest(exposure=exposure, uncertainty=uncertainty, now=now):
                with self.assertRaisesRegex(ValueError, "^clock_untrusted$"):
                    self.build(exposure, uncertainty, now)
