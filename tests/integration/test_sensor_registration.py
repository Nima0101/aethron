"""Independent geometric examples and withdrawal tests for rigid sensor registration."""

import importlib.util
import json
import math
import unittest


class SensorRegistration(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("aethron_edge.sensors.registration"))
        from aethron_edge.sensors import registration

        return registration

    def artifact(self, **changes):
        fields = {
            "version": 1,
            "source_frame": "radar_front",
            "target_frame": "front_optical",
            "mount_id": "rig_a",
            "evidence": "synthetic",
            "camera": {
                "width": 640,
                "height": 480,
                "fx": 400.0,
                "fy": 400.0,
                "cx": 320.0,
                "cy": 240.0,
            },
            "rotation": (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            "translation_m": (0.5, 0.0, 0.0),
            "translation_error_m": 0.01,
            "rotation_error_rad": 0.001,
            "reprojection_error_px": 0.25,
        }
        fields.update(changes)
        return self.api().RigCalibration.model_validate(fields)

    def binding(self, **changes):
        return self.api().Registration(
            self.artifact(**changes),
            now_ns=1_000_000_000,
            valid_for_ns=1_000_000_000,
            clock_id="boot_a",
        )

    def project(self, binding, point=(0.0, 0.0, 5.0), **changes):
        args = {
            "measurement_error_m": 0.02,
            "source_frame": "radar_front",
            "mount_id": "rig_a",
            "capture_ns": 1_010_000_000,
            "uncertainty_ns": 1_000_000,
            "clock_id": "boot_a",
            "now_ns": 1_020_000_000,
        }
        args.update(changes)
        return binding.project(point, **args)

    def test_active_calibration_cannot_be_replaced_without_rebinding(self):
        binding = self.binding()
        original = self.project(binding)
        with self.assertRaises(AttributeError):
            binding.calibration = self.artifact(translation_m=(0.0, 0.0, 0.0))
        current = self.project(binding)
        self.assertEqual(current.pixel, original.pixel)
        self.assertEqual(current.calibration_digest, original.calibration_digest)
        fresh = self.project(self.binding(translation_m=(0.0, 0.0, 0.0)))
        self.assertNotEqual(fresh.calibration_digest, original.calibration_digest)
        self.assertTrue(fresh.scene_break)

    def test_bound_projection_reuses_validated_digest_without_json_serialization(self):
        from unittest.mock import patch

        binding = self.binding()
        expected = binding.calibration.digest
        with patch.object(self.api().json, "dumps", side_effect=AssertionError("per_point_json")):
            for _ in range(4):
                result = self.project(binding)
                self.assertEqual(result.calibration_digest, expected)
                self.assertFalse(result.live_evidence)

    def test_translated_projection_uses_camera_frame_and_preserves_uncertainty(self):
        binding = self.binding()
        result = self.project(binding)
        self.assertEqual(result.camera_xyz_m, (0.5, 0.0, 5.0))
        self.assertEqual(result.pixel, (360.0, 240.0))
        self.assertEqual(result.normalized, (360 / 640, 0.5))
        self.assertAlmostEqual(result.range_m, math.sqrt(25.25))
        self.assertGreater(result.radius_m, 0.03)
        self.assertLess(result.pixel_bounds[0], 360)
        self.assertGreater(result.pixel_bounds[2], 360)
        self.assertFalse(result.live_evidence)
        self.assertEqual(result.expires_ns, 1_109_000_000)
        self.assertTrue(result.scene_break)
        self.assertFalse(self.project(binding).scene_break)

    def test_body_to_optical_rotation_and_inverse(self):
        # ROS body forward/left/up -> camera right/down/forward.
        artifact = self.artifact(
            rotation=(0.0, -1.0, 0.0, 0.0, 0.0, -1.0, 1.0, 0.0, 0.0), translation_m=(0.0, 0.0, 0.0)
        )
        self.assertEqual(artifact.transform((5.0, -1.0, -0.5)), (1.0, 0.5, 5.0))
        self.assertEqual(artifact.inverse((1.0, 0.5, 5.0)), (5.0, -1.0, -0.5))

    def test_rotation_scale_reflection_and_metadata_are_rejected(self):
        for changes in [
            {"rotation": (-1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)},
            {"rotation": (2.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)},
            {"rotation": (float("nan"),) * 9},
            {"translation_m": (True, 0.0, 0.0)},
            {"source_frame": "../secret"},
            {"evidence": "live"},
            {"person_id": "secret"},
            {"rotation_error_rad": -1.0},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.artifact(**changes)

    def test_binding_revalidates_copied_and_constructed_rig_calibration(self):
        api = self.api()
        artifact = self.artifact()
        for changes in [
            {"translation_error_m": -0.02},
            {"rotation_error_rad": -0.001},
            {"reprojection_error_px": -0.25},
            {"rotation": (-1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)},
            {"translation_m": (501.0, 0.0, 0.0)},
            {"evidence": "live"},
            {"source_frame": "private-sentinel/../frame"},
        ]:
            for calibration in (
                artifact.model_copy(update=changes),
                api.RigCalibration.model_construct(**(artifact.model_dump() | changes)),
            ):
                with self.subTest(changes=changes):
                    with self.assertRaisesRegex(ValueError, "^invalid_calibration$"):
                        api.Registration(calibration, now_ns=0, valid_for_ns=1, clock_id="boot_a")

    def test_binding_revalidates_nested_camera_and_rejects_incomplete_models(self):
        api = self.api()
        artifact = self.artifact()
        invalid = [api.RigCalibration.model_construct()]
        for changes in ({"fx": -400.0}, {"width": 0}, {"cx": float("nan")}):
            invalid.append(
                artifact.model_copy(update={"camera": artifact.camera.model_copy(update=changes)})
            )
        for calibration in invalid:
            with self.subTest(calibration=calibration):
                with self.assertRaisesRegex(ValueError, "^invalid_calibration$"):
                    api.Registration(calibration, now_ns=0, valid_for_ns=1, clock_id="boot_a")

    def test_stale_future_wrong_mount_frame_clock_and_expired_binding_withdraw(self):
        for changes in [
            {"capture_ns": 900_000_000},
            {"capture_ns": 1_021_000_000},
            {"uncertainty_ns": 50_000_001},
            {"mount_id": "rig_b"},
            {"source_frame": "other"},
            {"clock_id": "boot_b"},
            {"now_ns": 2_000_000_001, "capture_ns": 2_000_000_000},
        ]:
            binding = self.binding()
            self.project(binding)
            fault = self.project(binding, **changes)
            self.assertEqual(fault.reason, "registration_unavailable")
            self.assertTrue(fault.scene_break)

    def test_uncertain_plane_crossing_outside_image_and_invalid_points_withdraw(self):
        for point in [
            (0.0, 0.0, 0.01),
            (0.0, 0.0, -5.0),
            (20.0, 0.0, 5.0),
            (float("inf"), 0.0, 5.0),
            (10**400, 0.0, 5.0),
            (True, 0.0, 5.0),
            (0.0, 5.0),
        ]:
            self.assertEqual(self.project(self.binding(), point).reason, "registration_unavailable")
        binding = self.binding()
        self.project(binding)
        self.assertEqual(
            self.project(binding, measurement_error_m=10.0).reason, "registration_unavailable"
        )
        self.assertTrue(self.project(binding).scene_break)

    def test_projection_bounds_cover_independent_perturbed_points(self):
        result = self.project(self.binding())
        left, top, right, bottom = result.pixel_bounds
        # Perturb each source axis by less than declared total radius; direct pinhole arithmetic.
        for x, y, z in [
            (0.02, 0, 5),
            (-0.02, 0, 5),
            (0, 0.02, 5),
            (0, -0.02, 5),
            (0, 0, 4.98),
            (0, 0, 5.02),
        ]:
            u = 400 * (x + 0.5) / z + 320
            v = 400 * y / z + 240
            self.assertTrue(left <= u <= right and top <= v <= bottom)

    def test_digest_json_is_closed_bounded_and_deterministic(self):
        api = self.api()
        artifact = self.artifact()
        payload = artifact.model_dump_json().encode()
        self.assertEqual(api.load_calibration(payload).digest, artifact.digest)
        self.assertNotEqual(self.artifact(mount_id="rig_b").digest, artifact.digest)
        for invalid in [
            payload.replace(b'"version":1', b'"version":1,"version":1'),
            b" " * 16385,
            b"[" * 2000,
            json.dumps({"person_id": "secret"}).encode(),
        ]:
            with self.assertRaisesRegex(ValueError, "invalid_calibration"):
                api.load_calibration(invalid)

    def test_rebind_invalidates_previous_geometry_and_requires_new_clock_domain(self):
        binding = self.binding()
        self.project(binding)
        binding.close()
        self.assertEqual(self.project(binding).reason, "registration_unavailable")
        fresh = self.binding(translation_m=(0.0, 0.0, 0.0))
        result = self.project(fresh)
        self.assertEqual(result.pixel, (320.0, 240.0))
        self.assertTrue(result.scene_break)

    def test_2000_invalid_geometry_inputs_fail_closed_without_private_echo(self):
        import random

        rng = random.Random(77124)
        invalid = [True, None, "private-sentinel", float("nan"), float("inf"), 10**400]
        binding = self.binding()
        for _ in range(2000):
            point = [0.0, 0.0, 5.0]
            point[rng.randrange(3)] = rng.choice(invalid)
            result = self.project(binding, point)
            self.assertEqual(result.reason, "registration_unavailable")
            self.assertNotIn("private-sentinel", str(result))

    def test_monotonic_rewind_permanently_closes_binding(self):
        binding = self.binding()
        self.project(binding)
        fault = self.project(binding, now_ns=1_019_000_000)
        self.assertEqual(fault.reason, "registration_unavailable")
        self.assertEqual(self.project(binding).reason, "registration_unavailable")

    def test_rotation_error_footprint_covers_pose_perturbation(self):
        binding = self.binding(
            translation_error_m=0.0, rotation_error_rad=0.01, reprojection_error_px=0.0
        )
        result = self.project(binding, measurement_error_m=0.0)
        left, top, right, bottom = result.pixel_bounds
        # Independent physical perturbation: rotate source about camera y by ±.01 rad.
        for theta in (-0.01, 0.01):
            u = 400 * (5 * math.sin(theta) + 0.5) / (5 * math.cos(theta)) + 320
            self.assertLessEqual(left, u)
            self.assertGreaterEqual(right, u)
        self.assertLess(top, 240.0)
        self.assertGreater(bottom, 240.0)
