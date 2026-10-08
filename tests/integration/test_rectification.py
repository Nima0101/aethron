"""Actual installed OpenCV rectification, original analytical distorted rays."""

import importlib.util
import math
import unittest


class Rectification(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("aethron_edge.sensors.rectification"))
        from aethron_edge.sensors.rectification import LensCalibration

        return LensCalibration

    def lens(self, **changes):
        camera = {"width": 640, "height": 480, "fx": 400.0, "fy": 400.0, "cx": 320.0, "cy": 240.0}
        args = {
            "camera": camera,
            "output_camera": camera,
            "distortion": (0.1, 0.0, 0.0, 0.0, 0.0),
            "valid_radius": 1.0,
        }
        args.update(changes)
        return self.api().model_validate(args)

    def test_radial_undistortion_matches_analytical_ray_and_depth(self):
        # x=.2,y=.1,r^2=.05, k1=.1 -> xd=.201, yd=.1005.
        lens = self.lens()
        result = lens.rectify_points([(400.4, 280.2)])
        self.assertAlmostEqual(result[0][0], 400.0, places=6)
        self.assertAlmostEqual(result[0][1], 280.0, places=6)
        xyz = lens.deproject(400.4, 280.2, 5.0)
        for actual, expected in zip(xyz, (1.0, 0.5, 5.0), strict=True):
            self.assertAlmostEqual(actual, expected, places=7)

    def test_tangential_distortion_and_changed_output_intrinsics(self):
        camera = {"width": 320, "height": 240, "fx": 200.0, "fy": 200.0, "cx": 160.0, "cy": 120.0}
        # p1=.01,p2=-.02 at (.2,.1): delta=(-.0022,-.0001).
        lens = self.lens(distortion=(0.0, 0.0, 0.01, -0.02, 0.0), output_camera=camera)
        u, v = lens.rectify_points([(399.12, 279.96)])[0]
        self.assertAlmostEqual(u, 200.0, places=6)
        self.assertAlmostEqual(v, 140.0, places=6)

    def test_empty_bounded_input_and_invalid_coordinates_are_rejected(self):
        lens = self.lens()
        self.assertEqual(lens.rectify_points([]), [])
        for points in [
            [(320.0, 240.0)] * 4097,
            [(True, 0.0)],
            [(math.nan, 0.0)],
            [(640.0, 100.0)],
            [(10**400, 0.0)],
            [(1.0, 2.0, 3.0)],
        ]:
            with (
                self.subTest(points=str(points)[:40]),
                self.assertRaisesRegex(ValueError, "invalid_rectification"),
            ):
                lens.rectify_points(points)
        for depth in [0.0, -1.0, float("nan"), 501.0, True]:
            with self.assertRaisesRegex(ValueError, "invalid_rectification"):
                lens.deproject(320.0, 240.0, depth)

    def test_declared_radius_and_folded_lens_withdraw_geometry(self):
        with self.assertRaisesRegex(ValueError, "invalid_rectification"):
            self.lens(valid_radius=0.1).rectify_points([(400.4, 280.2)])
        # Strong barrel distortion folds radial mapping before r=1; reject calibration.
        with self.assertRaises(ValueError):
            self.lens(distortion=(-1.0, 0.0, 0.0, 0.0, 0.0))
        with self.assertRaises(ValueError):
            self.lens(distortion=(float("nan"),) * 5)

    def test_zero_distortion_identity_and_output_clipping(self):
        lens = self.lens(distortion=(0.0,) * 5)
        for actual, expected in zip(
            lens.rectify_points([(10.0, 20.0), (320.0, 240.0)]),
            [(10.0, 20.0), (320.0, 240.0)],
            strict=True,
        ):
            self.assertAlmostEqual(actual[0], expected[0], places=10)
            self.assertAlmostEqual(actual[1], expected[1], places=10)
        camera = {"width": 10, "height": 10, "fx": 400.0, "fy": 400.0, "cx": 5.0, "cy": 5.0}
        with self.assertRaisesRegex(ValueError, "invalid_rectification"):
            self.lens(output_camera=camera).rectify_points([(400.4, 280.2)])

    def test_raw_depth_bytes_to_rectified_rig_geometry(self):
        import struct

        from aethron_edge.sensors.packets import decode_image
        from aethron_edge.sensors.registration import Registration, RigCalibration

        raw = bytearray(640 * 480 * 2)
        struct.pack_into("<H", raw, (280 * 640 + 400) * 2, 5000)
        raster = decode_image(
            {
                "modality": "depth",
                "encoding": "16UC1",
                "width": 640,
                "height": 480,
                "step": 1280,
                "is_bigendian": False,
                "meters_per_unit": 0.001,
            },
            bytes(raw),
        )
        lens = self.lens(distortion=(0.0,) * 5)
        xyz = lens.deproject(400.0, 280.0, raster.depth_m(400, 280))
        rig = RigCalibration(
            version=1,
            source_frame="depth_optical",
            target_frame="rgb_optical",
            mount_id="bench",
            evidence="synthetic",
            camera=lens.output_camera,
            rotation=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            translation_m=(0.5, 0.0, 0.0),
            translation_error_m=0.01,
            rotation_error_rad=0.0,
            reprojection_error_px=0.1,
        )
        binding = Registration(
            rig, now_ns=1_000_000_000, valid_for_ns=1_000_000_000, clock_id="boot_a"
        )
        result = binding.project(
            xyz,
            measurement_error_m=0.005,
            source_frame="depth_optical",
            mount_id="bench",
            capture_ns=1_010_000_000,
            uncertainty_ns=0,
            clock_id="boot_a",
            now_ns=1_020_000_000,
        )
        self.assertEqual(result.pixel, (440.0, 280.0))
        self.assertFalse(result.live_evidence)
        with self.assertRaises(ValueError):
            lens.deproject(399.0, 280.0, raster.depth_m(399, 280))

    def test_recorded_provider_applies_lens_before_rigid_transform(self):
        from aethron_edge.sensors.geometry import Pinhole
        from aethron_edge.sensors.rectification import LensCalibration
        from test_sensor_provider import SensorProvider

        fixture = SensorProvider()
        fixture.setUp()
        fixture.camera = Pinhole(width=3, height=3, fx=1.6, fy=2.0, cx=1.0, cy=1.0)
        fixture.rig = fixture.rig.model_copy(
            update={"camera": Pinhole(width=7, height=7, fx=2.0, fy=2.0, cx=3.0, cy=3.0)}
        )
        lens = LensCalibration(
            camera=fixture.camera,
            output_camera=fixture.camera,
            distortion=(1.0, 0.0, 0.0, 0.0, 0.0),
            valid_radius=1.0,
        )
        provider = fixture.provider(lens=lens)
        result = provider.recorded(fixture.frame(provider.calibration), [(2, 1)], mount_id="rig_a")
        # Undistorted x=0.5 -> distorted x=0.625 -> u=2, at axial z=5.
        # Source x=2.5 m, then rig translation +0.5 m -> target pixel 4.2.
        self.assertAlmostEqual(result.points[0].camera_xyz_m[0], 3.0, places=8)
        self.assertAlmostEqual(result.points[0].pixel[0], 4.2, places=8)
        self.assertFalse(result.live_evidence)
