"""Raw ROS depth metadata must match a declared lens before correction."""

import copy
import inspect
import math
import struct
import unittest
from unittest.mock import patch

import test_sensor_provider as provider_fixture
from aethron_edge.sensors.geometry import Pinhole
from aethron_edge.sensors.rectification import FisheyeCalibration, LensCalibration
from aethron_edge.sensors.ros2 import ClockMapping, RosIngress
from aethron_edge.sources.base import SourceFault
from test_sensor_ros2 import camera, header


class RosLensBinding(unittest.TestCase):
    def setup_path(self, fisheye=True):
        self.fixture = f = provider_fixture.SensorProvider()
        f.setUp()
        out = Pinhole(width=7, height=7, fx=2.0, fy=2.0, cx=3.0, cy=3.0)
        f.rig = f.rig.model_copy(update={"camera": out})
        if fisheye:
            self.lens = FisheyeCalibration(
                model="opencv_fisheye_v1",
                camera=f.camera,
                output_camera=out,
                distortion=(0.0,) * 4,
                valid_theta_rad=0.8,
            )
        else:
            self.lens = LensCalibration(
                camera=f.camera,
                output_camera=out,
                distortion=(1.0, 0.0, 0.0, 0.0, 0.0),
                valid_radius=1.0,
            )
        self.assertIn("raw_depth_lens", inspect.signature(RosIngress).parameters)
        b = RosIngress(
            modality="depth",
            frame_id="depth_optical",
            meters_per_unit=0.001,
            raw_depth_lens=self.lens,
        )
        b.bind_clock(
            ClockMapping(
                domain="ros_system",
                offset_ns=0,
                uncertainty_ns=1_000_000,
                valid_until_ns=1_500_000_000,
            )
        )
        self.info = camera(
            header=header(1_010_000_000, "depth_optical"),
            width=3,
            height=3,
            distortion_model="equidistant" if fisheye else "plumb_bob",
            d=list(self.lens.distortion),
            k=[2.0, 0.0, 1.0, 0.0, 2.0, 1.0, 0.0, 0.0, 1.0],
            p=[2.0, 0.0, 3.0, 0.0, 0.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        )
        self.assertIsInstance(b.camera_info(self.info, now_ns=f.now, valid_for_ns=30_000_000), str)
        return b, f.provider(mode="ros", lens=self.lens)

    def image(self, b, stamp=1_010_000_000):
        return b.image(
            {
                "header": header(stamp, "depth_optical"),
                "width": 3,
                "height": 3,
                "encoding": "16UC1",
                "is_bigendian": 0,
                "step": 6,
                "data": struct.pack("<9H", *([5000] * 9)),
            },
            now_ns=self.fixture.now,
        )

    def test_declared_fisheye_raw_depth_is_corrected_once_before_rig(self):
        b, p = self.setup_path()
        self.image(b)
        r = p.ros(b, [(2, 1)], mount_id="rig_a")
        self.assertNotIsInstance(r, SourceFault)
        self.assertAlmostEqual(r.points[0].camera_xyz_m[0], 5 * math.tan(0.5) + 0.5)
        self.assertEqual(r.expires_ns, 1_050_000_000)
        self.assertEqual(r.source_evidence, "external_unverified")
        self.assertFalse(r.live_evidence)

    def test_declared_brown_raw_depth_is_corrected(self):
        b, p = self.setup_path(fisheye=False)
        self.image(b)
        r = p.ros(b, [(2, 1)], mount_id="rig_a")
        self.assertNotIsInstance(r, SourceFault)
        # x + x^3 = 0.5; this root is independent of the native inverse.
        x = r.points[0].camera_xyz_m[0] / 5 - 0.1
        self.assertAlmostEqual(x + x**3, 0.5, places=7)

    def test_mismatched_metadata_clears_pending_frame_and_available_geometry(self):
        for field, value in (
            ("d", [0.001, 0.0, 0.0, 0.0]),
            ("d", [False] * 4),
            ("distortion_model", "plumb_bob"),
            ("width", 4),
            ("k", [2.1, 0.0, 1.0, 0.0, 2.0, 1.0, 0.0, 0.0, 1.0]),
            ("p", [2.0, 0.0, 3.0, 0.1, 0.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, 0.0]),
            ("r", [0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]),
            ("binning_x", 2),
        ):
            with self.subTest(field=field, value=value):
                b, p = self.setup_path()
                self.image(b)
                self.assertNotIsInstance(p.ros(b, [(1, 1)], mount_id="rig_a"), SourceFault)
                self.image(b, stamp=1_011_000_000)
                bad = copy.deepcopy(self.info)
                bad[field] = value
                self.assertEqual(
                    b.camera_info(bad, now_ns=self.fixture.now).reason, "calibration_invalid"
                )
                self.assertIsNone(b.latest)
                self.assertFalse(p.status()["geometry_available"])

    def test_provider_cannot_apply_different_or_missing_lens(self):
        for mode in ("missing", "different"):
            b, _ = self.setup_path()
            lens = (
                None
                if mode == "missing"
                else self.lens.model_copy(update={"distortion": (0.001, 0.0, 0.0, 0.0)})
            )
            p = self.fixture.provider(mode="ros", lens=lens)
            self.image(b)
            self.assertEqual(p.ros(b, [(1, 1)], mount_id="rig_a").reason, "provider_unavailable")
            self.assertFalse(p.status()["geometry_available"])

    def test_default_ingress_still_refuses_distortion(self):
        b, _ = self.setup_path()
        plain = RosIngress(modality="depth", frame_id="depth_optical", meters_per_unit=0.001)
        self.assertEqual(
            plain.camera_info(self.info, now_ns=self.fixture.now).reason, "calibration_invalid"
        )
        for modality in ("nir", "lwir", "radar", "lidar"):
            with self.assertRaises(ValueError):
                RosIngress(modality=modality, frame_id="depth_optical", raw_depth_lens=self.lens)

    def test_rectified_ingress_cannot_be_corrected_again(self):
        _, p = self.setup_path()
        plain = self.fixture.ingress()
        self.assertEqual(p.ros(plain, [(1, 1)], mount_id="rig_a").reason, "provider_unavailable")

    def test_missing_native_rectifier_withdraws_geometry(self):
        b, p = self.setup_path()
        self.image(b)
        with patch.dict("sys.modules", {"cv2": None}):
            self.assertEqual(p.ros(b, [(1, 1)], mount_id="rig_a").reason, "provider_unavailable")
        self.assertFalse(p.status()["geometry_available"])

    def test_renewal_cannot_extend_queued_frame_calibration(self):
        b, p = self.setup_path()
        self.image(b)
        b.camera_info(self.info, now_ns=self.fixture.now, valid_for_ns=100_000_000)
        self.fixture.now = 1_050_000_001
        self.assertEqual(p.ros(b, [(1, 1)], mount_id="rig_a").reason, "provider_unavailable")
        self.assertFalse(p.status()["geometry_available"])

    def test_fresh_frame_after_renewal_has_new_lease(self):
        b, p = self.setup_path()
        self.image(b)
        self.assertNotIsInstance(p.ros(b, [(1, 1)], mount_id="rig_a"), SourceFault)
        self.fixture.now = 1_060_000_000
        b.camera_info(self.info, now_ns=self.fixture.now, valid_for_ns=100_000_000)
        self.image(b, stamp=1_059_000_000)
        r = p.ros(b, [(1, 1)], mount_id="rig_a")
        self.assertNotIsInstance(r, SourceFault)
        self.assertEqual(r.expires_ns, 1_158_000_000)
