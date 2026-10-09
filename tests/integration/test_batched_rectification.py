"""Bounded native work per depth frame; synthetic cost is not a latency benchmark."""

import math
import unittest
from unittest.mock import patch

import test_sensor_provider as provider_fixture
from aethron_edge.sensors.geometry import Pinhole
from aethron_edge.sensors.rectification import FisheyeCalibration, LensCalibration


class BatchedRectification(unittest.TestCase):
    def fixture(self, fisheye):
        f = provider_fixture.SensorProvider()
        f.setUp()
        output = Pinhole(width=7, height=7, fx=2.0, fy=2.0, cx=3.0, cy=3.0)
        f.rig = f.rig.model_copy(update={"camera": output})
        if fisheye:
            lens = FisheyeCalibration(
                model="opencv_fisheye_v1",
                camera=f.camera,
                output_camera=output,
                distortion=(0.0,) * 4,
                valid_theta_rad=1.0,
            )
        else:
            lens = LensCalibration(
                camera=f.camera,
                output_camera=output,
                distortion=(0.0,) * 5,
                valid_radius=1.0,
            )
        return f, f.provider(lens=lens)

    def test_native_call_overhead_does_not_multiply_by_selected_pixel_count(self):
        import cv2

        for fisheye in (False, True):
            with self.subTest(fisheye=fisheye):
                f, provider = self.fixture(fisheye)
                native = cv2.fisheye.undistortPoints if fisheye else cv2.undistortPointsIter

                def timed(*args, native=native, f=f, **kwargs):
                    result = native(*args, **kwargs)
                    f.now += 40_000_000  # Deterministic per-call cost, not a measured claim.
                    return result

                target = "cv2.fisheye.undistortPoints" if fisheye else "cv2.undistortPointsIter"
                with patch(target, side_effect=timed):
                    result = provider.recorded(
                        f.frame(provider.calibration), [(0, 1), (1, 1), (2, 1)], mount_id="rig_a"
                    )
                self.assertTrue(hasattr(result, "points"), result)
                x = 5 * math.tan(0.5) if fisheye else 2.5
                self.assertEqual(len(result.points), 3)
                for point, expected in zip(result.points, (-x + 0.5, 0.5, x + 0.5), strict=True):
                    self.assertAlmostEqual(point.camera_xyz_m[0], expected)
                self.assertEqual(result.expires_ns, 1_109_000_000)
                self.assertEqual(result.invalid_samples, 0)
                self.assertFalse(result.live_evidence)
                self.assertTrue(provider.status()["geometry_available"])

    def test_unknown_depths_preserve_selection_order_and_need_no_native_runtime(self):
        import hashlib
        import io
        import json
        import struct

        from aethron_edge.sensors.replay import read_frames

        for fisheye in (False, True):
            for all_unknown in (False, True):
                with self.subTest(fisheye=fisheye, all_unknown=all_unknown):
                    f, provider = self.fixture(fisheye)
                    values = [0] * 9
                    if not all_unknown:
                        values[3], values[5] = 3000, 4000
                    data = struct.pack("<9H", *values)
                    header = f.frame(provider.calibration).header.model_dump()
                    header["payload_sha256"] = hashlib.sha256(data).hexdigest()
                    raw = json.dumps(header).encode()
                    frame = next(read_frames(io.BytesIO(struct.pack(">I", len(raw)) + raw + data)))
                    # Empty input must not load OpenCV; nonempty paths use the real solver.
                    from contextlib import nullcontext

                    context = (
                        patch.dict("sys.modules", {"cv2": None}) if all_unknown else nullcontext()
                    )
                    with context:
                        result = provider.recorded(
                            frame, [(2, 1), (1, 1), (0, 1)], mount_id="rig_a"
                        )
                    self.assertEqual(result.invalid_samples, 3 if all_unknown else 1)
                    self.assertEqual(len(result.points), 0 if all_unknown else 2)
                    if not all_unknown:
                        ray = math.tan(0.5) if fisheye else 0.5
                        self.assertAlmostEqual(result.points[0].camera_xyz_m[0], 4 * ray + 0.5)
                        self.assertAlmostEqual(result.points[1].camera_xyz_m[0], -3 * ray + 0.5)
                    self.assertEqual(provider.status()["geometry_available"], not all_unknown)

    def test_native_overrun_still_withdraws_entire_batch(self):
        import cv2

        for fisheye in (False, True):
            with self.subTest(fisheye=fisheye):
                f, provider = self.fixture(fisheye)
                native = cv2.fisheye.undistortPoints if fisheye else cv2.undistortPointsIter

                def delayed(*args, native=native, f=f, **kwargs):
                    result = native(*args, **kwargs)
                    f.now += 100_000_000
                    return result

                target = "cv2.fisheye.undistortPoints" if fisheye else "cv2.undistortPointsIter"
                with patch(target, side_effect=delayed):
                    result = provider.recorded(
                        f.frame(provider.calibration), [(1, 1), (2, 1)], mount_id="rig_a"
                    )
                self.assertEqual(result.reason, "provider_unavailable")
                self.assertFalse(provider.status()["geometry_available"])
