"""Evidence admission must retain budget failures rather than round them away."""

import unittest

from scripts.world_technology_probe import summarize


class WorldTechnologyProbe(unittest.TestCase):
    def test_exact_frozen_budget_boundary(self):
        report = summarize([100.0] * 100, 32 * 1024 * 1024)
        self.assertTrue(report["within_frozen_resource_budget"])
        self.assertEqual(report["p95_ms"], 100)

    def test_small_excess_cannot_round_into_a_pass(self):
        for samples, peak in (([100.000001] * 100, 1), ([1.0] * 100, 33554433)):
            self.assertFalse(summarize(samples, peak)["within_frozen_resource_budget"])

    def test_invalid_or_incomplete_measurement_is_rejected(self):
        for samples in ([1.0] * 99, [float("nan")] * 100, [-1.0] * 100, [True] * 100):
            with self.assertRaises(ValueError):
                summarize(samples, 1)


if __name__ == "__main__":
    unittest.main()
