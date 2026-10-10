"""Synthetic scalar pinhole conformance; no physical calibration claims."""

import math
import unittest

from aethron_edge.sensors.geometry import Pinhole


class PinholeNumeric(unittest.TestCase):
    def setUp(self):
        self.camera = Pinhole(width=2, height=2, fx=1.0, fy=1.0, cx=0.0, cy=0.0)

    def test_range_preserves_tiny_finite_vectors(self):
        for value in (1e-300, math.ulp(0.0)):
            with self.subTest(value=value):
                self.assertEqual(self.camera.range_m((value, 0.0, 0.0)), value)

    def test_range_boundary_uses_euclidean_not_axial_distance(self):
        self.assertEqual(self.camera.range_m((300, 400, 0)), 500)
        for point in ((math.nextafter(500, math.inf), 0, 0), (1, 0, 500), (0, 0, 0)):
            with self.subTest(point=point), self.assertRaises(ValueError):
                self.camera.range_m(point)

    def test_pixel_boundary_does_not_round_outside_point_inward(self):
        self.assertEqual(self.camera.project((1, 1, 1)), (1, 1))
        for point in ((math.nextafter(1, math.inf), 0, 1), (math.nextafter(0, -math.inf), 0, 1)):
            with self.subTest(point=point), self.assertRaises(ValueError):
                self.camera.project(point)

    def test_overflow_and_nonfinite_results_fail_closed(self):
        extreme = Pinhole(width=2, height=2, fx=math.ulp(0.0), fy=1, cx=0, cy=0)
        with self.assertRaises(ValueError):
            extreme.deproject(1, 0, 500)
        for point in ((float("nan"), 0, 1), (0, 0, float("inf")), (0, 0, 10**400), (True, 0, 1)):
            with self.subTest(point=point), self.assertRaises(ValueError):
                self.camera.project(point)

    def test_scalar_round_trip_at_corners_and_small_depth(self):
        for u, v in ((0, 0), (0, 1), (1, 0), (1, 1)):
            for depth in (1e-300, 1.0, 500.0):
                with self.subTest(pixel=(u, v), depth=depth):
                    self.assertEqual(
                        self.camera.project(self.camera.deproject(u, v, depth)), (u, v)
                    )
