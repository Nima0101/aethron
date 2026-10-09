"""Synthetic sparse fisheye rays through installed rectification and raw replay."""

import math
import unittest
from unittest.mock import patch


class FisheyeRectification(unittest.TestCase):
    def lens(self, **changes):
        from aethron_edge.sensors import rectification

        self.assertTrue(hasattr(rectification, "FisheyeCalibration"), "fisheye model missing")
        camera = {"width": 640, "height": 480, "fx": 200.0, "fy": 200.0, "cx": 320.0, "cy": 240.0}
        fields = {
            "model": "opencv_fisheye_v1",
            "camera": camera,
            "output_camera": camera,
            "distortion": (0.01, -0.001, 0.0001, 0.0),
            "valid_theta_rad": 0.8,
        }
        fields.update(changes)
        return rectification.FisheyeCalibration.model_validate(fields)

    @staticmethod
    def project(lens, x, y):
        r = math.hypot(x, y)
        theta = math.atan(r)
        td = theta * (1 + sum(k * theta ** (2 * i) for i, k in enumerate(lens.distortion, 1)))
        scale = td / r if r else 1.0
        return (
            lens.camera.fx * scale * x + lens.camera.cx,
            lens.camera.fy * scale * y + lens.camera.cy,
        )

    def test_analytical_forward_rays_roundtrip_and_axial_depth(self):
        lens = self.lens()
        for x in (-0.4, -0.2, 0.0, 0.2, 0.4):
            for y in (-0.3, 0.0, 0.3):
                pixel = self.project(lens, x, y)
                actual = lens.rectify_points([pixel])[0]
                expected = lens.output_camera.project((x, y, 1.0))
                for a, b in zip(actual, expected, strict=True):
                    self.assertAlmostEqual(a, b, places=6)
                for a, b in zip(lens.deproject(*pixel, 5.0), (5 * x, 5 * y, 5.0), strict=True):
                    self.assertAlmostEqual(a, b, places=7)

    def test_zero_coefficients_are_equidistant_not_pinhole_identity(self):
        lens = self.lens(distortion=(0.0,) * 4)
        u = 320 + 200 * math.atan(0.5)
        self.assertAlmostEqual(lens.rectify_points([(u, 240.0)])[0][0], 420.0, places=6)
        self.assertEqual(lens.rectify_points([(320.0, 240.0)]), [(320.0, 240.0)])
        self.assertEqual(lens.rectify_points([]), [])

    def test_folded_ambiguous_or_unbounded_calibration_is_rejected(self):
        for changes in (
            {"distortion": (-1.0, 0.0, 0.0, 0.0)},
            {"distortion": (2.0, 2.0, 2.0, 2.0)},
            {"distortion": (math.nan, 0.0, 0.0, 0.0)},
            {"distortion": (0.0,) * 5},
            {"valid_theta_rad": math.pi / 2},
            {"valid_theta_rad": True},
            {"model": "guessed"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.lens(**changes)

    def test_input_domain_limits_and_output_crop(self):
        lens = self.lens(valid_theta_rad=0.1)
        for points in (
            [(350.0, 240.0)],
            [(True, 240.0)],
            [(math.nan, 0.0)],
            [(640.0, 0.0)],
            [(320.0, 240.0)] * 4097,
            [(1.0, 2.0, 3.0)],
        ):
            with self.assertRaisesRegex(ValueError, "invalid_rectification"):
                lens.rectify_points(points)
        for depth in (True, 0.0, 501.0, math.inf):
            with self.assertRaisesRegex(ValueError, "invalid_rectification"):
                lens.deproject(320.0, 240.0, depth)
        crop = {"width": 3, "height": 3, "fx": 200.0, "fy": 200.0, "cx": 1.0, "cy": 1.0}
        with self.assertRaisesRegex(ValueError, "invalid_rectification"):
            self.lens(output_camera=crop).rectify_points([(350.0, 240.0)])

    def test_inverse_result_must_pass_independent_forward_residual(self):
        import numpy as np

        lens = self.lens()
        with patch("cv2.fisheye.undistortPoints", return_value=np.array([[[0.2, 0.0]]])):
            with self.assertRaisesRegex(ValueError, "invalid_rectification"):
                lens.rectify_points([(320.0, 240.0)])

    def test_explicit_model_closed_schema_and_optional_runtime(self):
        from aethron_edge.sensors.rectification import FisheyeCalibration

        lens = self.lens()
        missing = lens.model_dump()
        del missing["model"]
        for fields in (missing, {**lens.model_dump(), "skew": 0.1}):
            with self.assertRaises(ValueError):
                FisheyeCalibration.model_validate(fields)
        with patch.dict("sys.modules", {"cv2": None}):
            with self.assertRaisesRegex(RuntimeError, "rectifier_unavailable"):
                lens.rectify_points([(320.0, 240.0)])

    def test_legacy_provider_digests_remain_byte_compatible(self):
        from aethron_edge.sensors.provider import ProviderCalibration
        from aethron_edge.sensors.rectification import LensCalibration
        from test_sensor_provider import SensorProvider

        fixture = SensorProvider()
        fixture.setUp()
        brown = LensCalibration(
            camera=fixture.camera,
            output_camera=fixture.camera,
            distortion=(0.0,) * 5,
            valid_radius=1.0,
        )
        # Captured from the installed pre-change 3a14963 wheel, not this implementation.
        for calibration, digest in (
            (fixture.config(), "6975173dbec73add6494850658d118664f9c62ddf4675572c17a15569efc7c89"),
            (
                fixture.config(lens=brown),
                "7292de94ba00ae87efe62925af0a337b01c45d9b484860598b43db8ec63c9ff1",
            ),
        ):
            self.assertEqual(calibration.digest, digest)
            restored = ProviderCalibration.model_validate_json(calibration.model_dump_json())
            self.assertEqual(restored.digest, digest)

    def test_recorded_provider_binds_fisheye_and_preserves_expiry(self):
        from aethron_edge.sensors.geometry import Pinhole
        from aethron_edge.sensors.provider import ProviderCalibration
        from test_sensor_provider import SensorProvider

        fixture = SensorProvider()
        fixture.setUp()
        fixture.camera = Pinhole(width=3, height=3, fx=2.0, fy=2.0, cx=1.0, cy=1.0)
        output = Pinhole(width=7, height=7, fx=2.0, fy=2.0, cx=3.0, cy=3.0)
        fixture.rig = fixture.rig.model_copy(update={"camera": output})
        lens = self.lens(camera=fixture.camera, output_camera=output, distortion=(0.0,) * 4)
        provider = fixture.provider(lens=lens)
        config = provider.calibration
        restored = ProviderCalibration.model_validate_json(config.model_dump_json())
        self.assertEqual(restored.digest, config.digest)
        self.assertEqual(restored.lens.model, "opencv_fisheye_v1")
        changed = fixture.config(
            lens=self.lens(
                camera=fixture.camera, output_camera=output, distortion=(0.001, 0.0, 0.0, 0.0)
            )
        )
        self.assertNotEqual(changed.digest, config.digest)
        result = provider.recorded(fixture.frame(config), [(2, 1)], mount_id="rig_a")
        self.assertAlmostEqual(result.points[0].camera_xyz_m[0], 5 * math.tan(0.5) + 0.5)
        self.assertEqual(result.expires_ns, 1_109_000_000)
        self.assertFalse(result.live_evidence)
        fixture.now = 1_120_000_000
        self.assertFalse(provider.status()["geometry_available"])
        with self.assertRaises(ValueError):
            fixture.config(lens=lens, source_camera=output)
