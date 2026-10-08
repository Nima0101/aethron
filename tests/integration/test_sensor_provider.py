"""Real raw packets through calibrated provider admission; no inferred object classes."""

import hashlib
import importlib.util
import io
import json
import struct
import unittest

from aethron_edge.sensors.geometry import Pinhole
from aethron_edge.sensors.packets import ImageLayout
from aethron_edge.sensors.registration import RigCalibration
from aethron_edge.sensors.replay import read_frames
from aethron_edge.sensors.ros2 import ClockMapping, RosIngress


class SensorProvider(unittest.TestCase):
    def setUp(self):
        self.now = 1_020_000_000
        self.camera = Pinhole(width=3, height=3, fx=2.0, fy=2.0, cx=1.0, cy=1.0)
        self.layout = ImageLayout(
            modality="depth",
            encoding="16UC1",
            width=3,
            height=3,
            step=6,
            is_bigendian=False,
            meters_per_unit=0.001,
        )
        self.rig = RigCalibration(
            version=1,
            source_frame="depth_optical",
            target_frame="front_optical",
            mount_id="rig_a",
            evidence="synthetic",
            camera=self.camera,
            rotation=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            translation_m=(0.5, 0.0, 0.0),
            translation_error_m=0.01,
            rotation_error_rad=0.0,
            reprojection_error_px=0.0,
        )

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("aethron_edge.sensors.provider"))
        from aethron_edge.sensors import provider

        return provider

    def config(self, **changes):
        api = self.api()
        fields = {
            "source_id": "depth_front",
            "modality": "depth",
            "rig": self.rig,
            "source_camera": self.camera,
            "lens": None,
            "measurement_error_m": 0.01,
            "layout_sha256": api.layout_digest(self.layout),
        }
        fields.update(changes)
        return api.ProviderCalibration(**fields)

    def provider(self, mode="recorded", **changes):
        return self.api().GeometryProvider(
            self.config(**changes),
            mode=mode,
            clock_id="recording_a" if mode == "recorded" else "boot_a",
            clock=lambda: self.now,
            valid_for_ns=500_000_000,
        )

    def frame(self, config, *, stamp=1_010_000_000, sequence=1, **changes):
        data = struct.pack("<9H", *([5000] * 9))
        header = {
            "version": 1,
            "source_id": "depth_front",
            "sequence": sequence,
            "acquisition_ns": stamp,
            "clock_domain": "recorded_monotonic",
            "uncertainty_ns": 1_000_000,
            "coordinate_frame": "depth_optical",
            "modality": "depth",
            "calibration_sha256": config.digest,
            "payload_sha256": hashlib.sha256(data).hexdigest(),
            "layout": self.layout.model_dump(),
        }
        header.update(changes)
        raw = json.dumps(header).encode()
        return next(read_frames(io.BytesIO(struct.pack(">I", len(raw)) + raw + data)))

    def test_recorded_depth_projects_measured_range_with_bound_provenance(self):
        p = self.provider()
        result = p.recorded(self.frame(p.calibration), [(1, 1)], mount_id="rig_a")
        self.assertEqual(result.points[0].camera_xyz_m, (0.5, 0.0, 5.0))
        self.assertEqual(result.points[0].pixel, (1.2, 1.0))
        self.assertEqual(result.expires_ns, 1_109_000_000)
        self.assertEqual(result.calibration_digest, p.calibration.digest)
        self.assertEqual(result.source_evidence, "recorded")
        self.assertFalse(result.live_evidence)
        self.assertTrue(result.scene_break)
        self.assertEqual(p.status()["state"], "UNKNOWN")
        self.assertTrue(p.status()["geometry_available"])
        self.now = 1_120_000_000
        self.assertFalse(p.status()["geometry_available"])

    def test_changed_source_layout_or_calibration_cannot_reuse_geometry(self):
        for change in (
            {"source_id": "different"},
            {"calibration_sha256": "0" * 64},
            {"coordinate_frame": "other"},
            {"layout": self.layout.model_copy(update={"meters_per_unit": 0.002}).model_dump()},
        ):
            with self.subTest(change=change):
                p = self.provider()
                self.assertTrue(
                    p.recorded(self.frame(p.calibration), [(1, 1)], mount_id="rig_a").points
                )
                bad = self.frame(p.calibration, stamp=1_011_000_000, sequence=2, **change)
                self.assertEqual(
                    p.recorded(bad, [(1, 1)], mount_id="rig_a").reason, "provider_unavailable"
                )
                self.assertFalse(p.status()["geometry_available"])
                good = self.frame(p.calibration, stamp=1_012_000_000, sequence=3)
                self.assertTrue(p.recorded(good, [(1, 1)], mount_id="rig_a").scene_break)

    def test_duplicate_future_stale_and_mount_change_withdraw(self):
        p = self.provider()
        f = self.frame(p.calibration)
        p.recorded(f, [(1, 1)], mount_id="rig_a")
        self.assertEqual(p.recorded(f, [(1, 1)], mount_id="rig_a").reason, "provider_unavailable")
        for stamp in (1_021_000_000, 900_000_000):
            p = self.provider()
            self.assertEqual(
                p.recorded(
                    self.frame(p.calibration, stamp=stamp), [(1, 1)], mount_id="rig_a"
                ).reason,
                "provider_unavailable",
            )
        p = self.provider()
        self.assertEqual(
            p.recorded(self.frame(p.calibration), [(1, 1)], mount_id="moved").reason,
            "provider_unavailable",
        )
        self.assertEqual(
            p.recorded(self.frame(p.calibration), [(1, 1)], mount_id="rig_a").reason,
            "provider_unavailable",
        )

    def test_bounded_selection_and_lost_rewind_close(self):
        for indices in ([(1, 1)] * 65, [(True, 1)], [(3, 0)], [(1, 1), (1, 1)]):
            p = self.provider()
            self.assertEqual(
                p.recorded(self.frame(p.calibration), indices, mount_id="rig_a").reason,
                "provider_unavailable",
            )
        p = self.provider()
        p.recorded(self.frame(p.calibration), [(1, 1)], mount_id="rig_a")
        p.source_lost()
        self.assertFalse(p.status()["geometry_available"])
        self.now += 1_000_000
        self.assertTrue(
            p.recorded(
                self.frame(p.calibration, stamp=1_012_000_000, sequence=2),
                [(1, 1)],
                mount_id="rig_a",
            ).scene_break
        )
        self.now -= 20_000_000
        self.assertFalse(p.status()["geometry_available"])
        self.now += 30_000_000
        self.assertEqual(
            p.recorded(
                self.frame(p.calibration, stamp=1_015_000_000, sequence=3),
                [(1, 1)],
                mount_id="rig_a",
            ).reason,
            "provider_unavailable",
        )

    def ingress(self):
        b = RosIngress(modality="depth", frame_id="depth_optical", meters_per_unit=0.001)
        b.bind_clock(
            ClockMapping(
                domain="ros_system",
                offset_ns=0,
                uncertainty_ns=1_000_000,
                valid_until_ns=1_060_000_000,
            )
        )
        h = {"frame_id": "depth_optical", "stamp": {"sec": 1, "nanosec": 10_000_000}}
        info = {
            "header": h,
            "width": 3,
            "height": 3,
            "distortion_model": "plumb_bob",
            "d": [0.0] * 5,
            "k": [2.0, 0.0, 1.0, 0.0, 2.0, 1.0, 0.0, 0.0, 1.0],
            "r": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
            "p": [2.0, 0.0, 1.0, 0.0, 0.0, 2.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0],
            "binning_x": 0,
            "binning_y": 0,
            "roi": {"x_offset": 0, "y_offset": 0, "height": 0, "width": 0, "do_rectify": False},
        }
        b.camera_info(info, now_ns=self.now, valid_for_ns=30_000_000)
        b.image(
            {
                "header": h,
                "width": 3,
                "height": 3,
                "encoding": "16UC1",
                "is_bigendian": 0,
                "step": 6,
                "data": struct.pack("<9H", *([5000] * 9)),
            },
            now_ns=self.now,
        )
        return b

    def test_real_ros_ingress_mapping_and_intrinsics_expiry_bound_result(self):
        p = self.provider(mode="ros")
        b = self.ingress()
        result = p.ros(b, [(1, 1)], mount_id="rig_a")
        self.assertEqual(result.points[0].pixel, (1.2, 1.0))
        self.assertEqual(result.expires_ns, 1_050_000_000)
        self.assertEqual(result.source_evidence, "external_unverified")
        self.assertFalse(result.live_evidence)
        self.now = 1_051_000_000
        self.assertFalse(p.status()["geometry_available"])

    def test_missing_mapping_expired_intrinsics_and_cross_mode_do_not_promote(self):
        for cause in ("clock", "calibration", "source"):
            p = self.provider(mode="ros")
            b = self.ingress()
            if cause == "clock":
                b.bind_clock(
                    ClockMapping(
                        domain="ros_system", offset_ns=0, uncertainty_ns=1_000_000, valid_until_ns=1
                    )
                )
            elif cause == "calibration":
                self.now += 31_000_000
            else:
                p.ros(b, [(1, 1)], mount_id="rig_a")
                b = self.ingress()
            self.assertEqual(p.ros(b, [(1, 1)], mount_id="rig_a").reason, "provider_unavailable")
            self.now = 1_020_000_000
        p = self.provider(mode="ros")
        self.assertEqual(
            p.recorded(self.frame(p.calibration), [(1, 1)], mount_id="rig_a").reason,
            "provider_unavailable",
        )

    def test_ros_cloud_format_is_bound_but_point_count_may_change(self):
        from aethron_edge.sensors.packets import CloudLayout

        fields = [
            {"name": n, "offset": i * 4, "datatype": 7, "count": 1}
            for i, n in enumerate(("x", "y", "z"))
        ]
        layout = CloudLayout(
            width=1, height=1, point_step=12, row_step=12, is_bigendian=False, fields=fields
        )
        api = self.api()
        larger = CloudLayout.model_validate({**layout.model_dump(), "width": 2, "row_step": 24})
        self.assertEqual(api.layout_digest(layout), api.layout_digest(larger))
        cfg = self.config(
            modality="radar", source_camera=None, layout_sha256=api.layout_digest(layout)
        )
        p = api.GeometryProvider(
            cfg, mode="ros", clock_id="boot_a", clock=lambda: self.now, valid_for_ns=500_000_000
        )
        b = RosIngress(modality="radar", frame_id="depth_optical")
        b.bind_clock(
            ClockMapping(
                domain="ros_system",
                offset_ns=0,
                uncertainty_ns=1_000_000,
                valid_until_ns=1_500_000_000,
            )
        )
        for count in (1, 2):
            stamp = 1_009_000_000 + count * 1_000_000
            msg = {
                "header": {
                    "frame_id": "depth_optical",
                    "stamp": {"sec": 1, "nanosec": stamp - 1_000_000_000},
                },
                "width": count,
                "height": 1,
                "fields": fields,
                "is_bigendian": False,
                "point_step": 12,
                "row_step": count * 12,
                "is_dense": True,
                "data": struct.pack("<" + "fff" * count, *([0.0, 0.0, 5.0] * count)),
            }
            b.pointcloud(msg, now_ns=self.now)
            result = p.ros(b, list(range(count)), mount_id="rig_a")
            self.assertEqual(len(result.points), count)
            self.assertEqual(result.points[0].pixel, (1.2, 1.0))
        msg.update(is_bigendian=True)
        msg["header"]["stamp"]["nanosec"] = 12_000_000
        b.pointcloud(msg, now_ns=self.now)
        self.assertEqual(p.ros(b, [0], mount_id="rig_a").reason, "provider_unavailable")

    def test_processing_deadline_and_invalid_clock_withdraw(self):
        p = self.provider()
        f = self.frame(p.calibration)
        times = iter([1_020_000_000, 1_120_000_000])
        p.clock = lambda: next(times)
        self.assertEqual(p.recorded(f, [(1, 1)], mount_id="rig_a").reason, "provider_unavailable")
        p = self.provider()
        p.clock = lambda: True
        self.assertEqual(p.recorded(f, [(1, 1)], mount_id="rig_a").reason, "provider_unavailable")
        p.clock = lambda: 1_020_000_000
        self.assertEqual(p.recorded(f, [(1, 1)], mount_id="rig_a").reason, "provider_unavailable")

    def test_malformed_decoded_payload_withdraws_without_parser_exception(self):
        from dataclasses import replace

        from aethron_edge.sensors.packets import Raster

        provider = self.provider()
        frame = self.frame(provider.calibration)
        malformed = replace(frame, payload=Raster(self.layout, b"x"))
        self.assertEqual(
            provider.recorded(malformed, [(1, 1)], mount_id="rig_a").reason, "provider_unavailable"
        )

    def test_adversarial_selection_never_creates_geometry(self):
        import random

        rng = random.Random(20261008)
        for _ in range(2000):
            provider = self.provider()
            frame = self.frame(provider.calibration)
            index = (rng.choice([-10, -1, 3, 10**100]), rng.randrange(3))
            result = provider.recorded(frame, [index], mount_id="rig_a")
            self.assertEqual(result.reason, "provider_unavailable")
            self.assertFalse(provider.status()["geometry_available"])
