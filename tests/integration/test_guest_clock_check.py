"""Bounded read-only guest diagnostics preserve the ROS clock drift rule."""

import importlib.util
import json
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "packaging/appliance/image/clock_check.py"


def probe():
    spec = importlib.util.spec_from_file_location("clock_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def clocks(offsets, duration=1000):
    # All absolute epochs stay local to the fake clocks and out of the report.
    epochs = [10_000_000_000 + i * 20_000_000 for i in range(len(offsets))]
    monotonic = iter(v for before in epochs for v in (before, before + duration))
    wall = iter(before + duration // 2 - offset for before, offset in zip(epochs, offsets))
    return lambda: next(monotonic), lambda: next(wall)


class GuestClockCheck(unittest.TestCase):
    def run_probe(self, offsets, duration=1000):
        module = probe()
        monotonic, realtime = clocks(offsets, duration)
        sleeps = []
        result = module.check(
            samples=len(offsets), monotonic=monotonic, realtime=realtime, sleep=sleeps.append
        )
        self.assertEqual(sleeps, [0.02] * (len(offsets) - 1))
        return result

    def test_captured_offset_step_is_rejected_without_baseline_reset(self):
        result = self.run_probe([0, -7_418_465, -7_418_215, 0])
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["rejected_samples"], 2)
        self.assertEqual(result["max_abs_offset_delta_ns"], 7_418_465)
        self.assertEqual(result["first_rejections"][0]["offset_delta_ns"], -7_418_465)
        self.assertEqual(result["first_rejections"][1]["index"], 2)
        self.assertFalse(result["qualified"])

    def test_exact_budget_and_one_nanosecond_over(self):
        self.assertEqual(self.run_probe([0, 1_000_000])["status"], "within_budget")
        result = self.run_probe([0, 1_000_001])
        self.assertEqual(result["first_rejections"][0]["reason"], "clock_drift")
        self.assertEqual(result["budget_ns"], 1_000_000)

    def test_output_is_bounded_and_contains_no_raw_epochs(self):
        result = self.run_probe([0] + [7_418_465] * 49)
        self.assertEqual(result["samples"], 50)
        self.assertEqual(result["rejected_samples"], 49)
        self.assertEqual(len(result["first_rejections"]), 8)
        self.assertLess(len(json.dumps(result)), 2500)
        self.assertNotIn("10000000000", json.dumps(result))
        self.assertEqual(
            set(result["first_rejections"][0]),
            {"index", "reason", "offset_delta_ns", "sample_error_ns"},
        )

    def test_invalid_initial_sample_stops_without_selecting_a_new_anchor(self):
        module = probe()
        ticks = iter([10, 1_000_011])
        sleeps = []
        result = module.check(
            samples=3, monotonic=lambda: next(ticks), realtime=lambda: 10, sleep=sleeps.append
        )
        self.assertEqual(result["samples"], 1)
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["first_rejections"][0]["reason"], "clock_sample_invalid")
        self.assertEqual(sleeps, [])

    def test_later_invalid_sample_and_rewind_cannot_be_erased_by_recovery(self):
        for ticks, walls, reason in (
            (
                [10_000_000, 10_001_000, 30_000_000, 31_000_001, 50_000_000, 50_001_000],
                [10_000_500, 30_000_500, 50_000_500],
                "clock_sample_invalid",
            ),
            (
                [10_000_000, 10_001_000, 9_000_000, 9_001_000, 50_000_000, 50_001_000],
                [10_000_500, 9_000_500, 50_000_500],
                "clock_rewind",
            ),
        ):
            with self.subTest(reason=reason):
                mono, wall = iter(ticks), iter(walls)
                result = probe().check(
                    samples=3,
                    monotonic=lambda mono=mono: next(mono),
                    realtime=lambda wall=wall: next(wall),
                    sleep=lambda _: None,
                )
                self.assertEqual(result["samples"], 3)
                self.assertEqual(result["status"], "rejected")
                self.assertEqual(result["rejected_samples"], 1)
                self.assertEqual(result["first_rejections"][0]["reason"], reason)

    def test_initial_uncertainty_is_included_without_accumulating_drift(self):
        # Anchor error688ns; next error500ns. The budget permits1000188ns,
        # but1000189ns is one nanosecond outside that same original anchor.
        ticks = iter([10_000_000, 10_001_376, 30_000_000, 30_001_000, 50_000_000, 50_001_000])
        walls = iter([10_000_688, 30_000_500 - 1_000_188, 50_000_500 - 1_000_189])
        result = probe().check(
            samples=3,
            monotonic=lambda: next(ticks),
            realtime=lambda: next(walls),
            sleep=lambda _: None,
        )
        self.assertEqual(result["baseline_sample_error_ns"], 688)
        self.assertEqual(result["rejected_samples"], 1)
        self.assertEqual(result["first_rejections"][0]["index"], 2)

    def test_count_rejected_before_touching_clocks(self):
        def forbidden():
            self.fail("clock sampled for invalid request")

        for count in (True, 1, 1502, 2.0):
            with self.subTest(count=count), self.assertRaises(ValueError):
                probe().check(samples=count, monotonic=forbidden, realtime=forbidden)
