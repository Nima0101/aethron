import math
import unittest
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction

from aethron_edge.calibration import CalibrationRecord
from aethron_edge.pipeline import build_v3
from aethron_edge.sources.base import FrameEnvelope
from aethron_edge.timebase import MappedFrame


class CalibrationAdmission(unittest.TestCase):
    def setUp(self):
        self.record = CalibrationRecord(
            "bench", 2, 2, 2000, "mount-a", (1, 0, 0, 0, 1, 0, 0, 0, 1), 0.001
        )
        self.frame = FrameEnvelope(
            b"\0" * 12,
            2,
            2,
            1,
            1_000_000_000,
            1_000_000_000,
            "host_monotonic",
            0,
            "bench",
        )

    def test_invalid_time_and_dimensions_reject_without_coercion(self):
        bad = (True, False, -1, 0.5, float("nan"), float("inf"), None, "2")
        for value in bad:
            with self.subTest(now=value):
                self.assertIs(self.record.valid_for(self.frame, value, "mount-a"), False)
            for field in ("width", "height", "valid_until_ms"):
                with self.subTest(record_field=field, value=value):
                    record = replace(self.record, **{field: value})
                    frame = (
                        replace(self.frame, **{field: value})
                        if field != "valid_until_ms"
                        else self.frame
                    )
                    self.assertIs(record.valid_for(frame, 0, "mount-a"), False)
        for field in ("width", "height"):
            for value in (0, 2.0):
                with self.subTest(field=field, value=value):
                    self.assertFalse(
                        replace(self.record, **{field: value}).valid_for(
                            replace(self.frame, **{field: value}), 1000, "mount-a"
                        )
                    )
                    self.assertFalse(
                        self.record.valid_for(
                            replace(self.frame, **{field: value}), 1000, "mount-a"
                        )
                    )
        self.assertFalse(
            replace(self.record, valid_until_ms=2000.0).valid_for(self.frame, 1000, "mount-a")
        )

    def test_missing_identity_cannot_match_itself(self):
        for value in (None, "", False, 0):
            with self.subTest(value=value):
                self.assertFalse(
                    replace(self.record, calibration_id=value).valid_for(
                        replace(self.frame, calibration_id=value), 1000, "mount-a"
                    )
                )
                self.assertFalse(
                    replace(self.record, mount_id=value).valid_for(self.frame, 1000, value)
                )

    def test_transform_and_residual_require_real_numbers(self):
        for value in (
            False,
            True,
            None,
            "0",
            float("nan"),
            float("inf"),
            -0.01,
            0.051,
            Decimal("0.001"),
            Fraction(1, 1000),
            10**1000,
        ):
            with self.subTest(residual=value):
                self.assertIs(
                    replace(self.record, residual=value).valid_for(self.frame, 1000, "mount-a"),
                    False,
                )
        for index, coefficient in enumerate(self.record.transform):
            for value in (
                bool(coefficient),
                None,
                str(coefficient),
                float("nan"),
                float("inf"),
                Decimal(coefficient),
                Fraction(coefficient),
            ):
                with self.subTest(index=index, value=value):
                    transform = list(self.record.transform)
                    transform[index] = value
                    self.assertFalse(
                        replace(self.record, transform=tuple(transform)).valid_for(
                            self.frame, 1000, "mount-a"
                        )
                    )
        for value in (None, (), self.record.transform[:-1], list(self.record.transform)):
            self.assertFalse(
                replace(self.record, transform=value).valid_for(self.frame, 1000, "mount-a")
            )

    def test_exact_bounds_and_numeric_identity_still_pass(self):
        self.assertEqual(
            self.record.digest, "c71f963ddd5489ded257be4a80b80d6a0a334d0caffa23bfc4c90c79da63b1e7"
        )
        for expiry in (0, 2000, 2**100):
            for residual in (0, 0.0, 0.05):
                record = replace(
                    self.record,
                    valid_until_ms=expiry,
                    residual=residual,
                    transform=tuple(float(v) for v in self.record.transform),
                )
                self.assertTrue(record.valid_for(self.frame, expiry, "mount-a"))
                self.assertFalse(record.valid_for(self.frame, expiry + 1, "mount-a"))
        self.assertFalse(
            replace(self.record, residual=math.nextafter(0.05, math.inf)).valid_for(
                self.frame, 1000, "mount-a"
            )
        )

    def test_invalid_calibration_never_emits_registered_observation(self):
        for record in (
            replace(self.record, residual=False),
            replace(self.record, valid_until_ms=float("inf")),
            replace(self.record, width=2.0),
        ):
            with self.subTest(record=record):
                with self.assertRaisesRegex(ValueError, "^calibration_expired$"):
                    build_v3(
                        MappedFrame(self.frame, 1_000_000_000, 0),
                        [],
                        record,
                        now_ns=1_000_000_000,
                        mount_id="mount-a",
                    )
