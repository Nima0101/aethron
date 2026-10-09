"""Portable ROS message-boundary tests; actual DDS is a separate installed check."""

import importlib.util
import struct
import unittest
from array import array


def header(stamp=1_000_000_000, frame="front_optical"):
    return {
        "stamp": {"sec": stamp // 1_000_000_000, "nanosec": stamp % 1_000_000_000},
        "frame_id": frame,
    }


def image(stamp=1_000_000_000, **changes):
    value = {
        "header": header(stamp),
        "height": 1,
        "width": 2,
        "encoding": "16UC1",
        "is_bigendian": 0,
        "step": 4,
        "data": array("B", struct.pack("<HH", 0, 2500)),
    }
    value.update(changes)
    return value


def camera(**changes):
    value = {
        "header": header(),
        "height": 1,
        "width": 2,
        "distortion_model": "plumb_bob",
        "d": [0.0] * 5,
        "k": [2.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 1.0],
        "r": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        "p": [2.0, 0.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        "binning_x": 0,
        "binning_y": 0,
        "roi": {"x_offset": 0, "y_offset": 0, "height": 0, "width": 0, "do_rectify": False},
    }
    value.update(changes)
    return value


class RosSensors(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("aethron_edge.sensors.ros2"))
        from aethron_edge.sensors import ros2

        return ros2

    def bridge(self):
        return self.api().RosIngress(
            modality="depth", frame_id="front_optical", meters_per_unit=0.002
        )

    def test_captured_guest_source_step_withdraws_mapped_observation(self):
        api = self.api()
        bridge = self.bridge()
        bridge.bind_clock(
            api.ClockMapping(
                domain="ros_system",
                offset_ns=0,
                uncertainty_ns=2_000_688,
                valid_until_ns=5_000_000_000,
            )
        )
        # Captured deltas: receipt+20.404041ms, source+27.894445ms,
        # resulting age -2.160424ms. Absolute host/source timestamps omitted.
        initial = 1_000_000_000
        received = initial + 5_329_980
        first = bridge.image(image(initial), now_ns=received)
        self.assertEqual(first.capture_ns, initial)
        result = bridge.image(image(initial + 27_894_445), now_ns=received + 20_404_041)
        self.assertEqual(result.reason, "clock_discontinuity")
        self.assertIsNone(bridge.mapping)
        self.assertIsNone(bridge.latest)
        # A later sane frame alone cannot invent a replacement clock mapping.
        later = bridge.image(image(initial + 40_000_000), now_ns=received + 50_000_000)
        self.assertIsNone(later.capture_ns)
        self.assertIsNone(bridge.mapping)

    def test_depth_bytes_and_received_clock_do_not_invent_live_support(self):
        b = self.bridge()
        result = b.image(image(), now_ns=2_000_000_000)
        self.assertEqual(result.payload.depth_m(1, 0), 5)
        self.assertEqual(result.stamp_ns, 1_000_000_000)
        self.assertIsNone(result.capture_ns)
        self.assertFalse(result.live_evidence)
        self.assertIs(b.take(now_ns=2_010_000_000), result)
        self.assertEqual(b.take(now_ns=2_010_000_001).reason, "source_waiting")
        self.assertEqual(b.status(now_ns=2_200_000_000)["source_state"], "lost")

    def test_intrinsics_match_and_configuration_change_erases_pending_frame(self):
        b = self.bridge()
        b.camera_info(camera(), now_ns=2_000_000_000)
        r = b.image(image(), now_ns=2_000_000_001)
        self.assertIsNotNone(r.calibration_digest)
        self.assertEqual(r.camera.deproject(1, 0, 5), (2.5, 0.0, 5.0))
        changed = camera(
            k=[3.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 1.0],
            p=[3.0, 0.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
        )
        b.camera_info(changed, now_ns=2_010_000_000)
        self.assertEqual(b.take(now_ns=2_010_000_001).reason, "source_waiting")
        r2 = b.image(image(1_020_000_000), now_ns=2_020_000_000)
        self.assertNotEqual(r.calibration_digest, r2.calibration_digest)
        self.assertTrue(r2.scene_break)

    def test_resolution_mismatch_calibration_expiry_and_bad_info_clear_calibration(self):
        b = self.bridge()
        b.camera_info(camera(), now_ns=2_000_000_000, valid_for_ns=50_000_000)
        r = b.image(image(), now_ns=2_060_000_000)
        self.assertIsNone(r.camera)
        b.camera_info(camera(width=3), now_ns=2_070_000_000)
        r = b.image(image(1_070_000_000), now_ns=2_070_000_001)
        self.assertIsNone(r.camera)
        for invalid in (
            camera(d=[0.1] * 5),
            camera(k=[0.0] * 9),
            camera(binning_x=2),
            camera(person_id="secret"),
        ):
            fault = b.camera_info(invalid, now_ns=2_080_000_000)
            self.assertEqual(fault.reason, "calibration_invalid")
            self.assertNotIn("secret", str(fault))

    def test_explicit_mapping_expires_and_simulation_is_not_trusted(self):
        api = self.api()
        b = self.bridge()
        mapping = api.ClockMapping(
            domain="ros_system",
            offset_ns=1_000_000_000,
            uncertainty_ns=1_000_000,
            valid_until_ns=2_100_000_000,
        )
        b.bind_clock(mapping)
        r = b.image(image(), now_ns=2_010_000_000)
        self.assertEqual(r.capture_ns, 2_000_000_000)
        self.assertFalse(r.live_evidence)
        r = b.image(image(1_110_000_000), now_ns=2_120_000_000)
        self.assertIsNone(r.capture_ns)
        with self.assertRaises(ValueError):
            api.ClockMapping(
                domain="ros_simulation", offset_ns=1, uncertainty_ns=0, valid_until_ns=2
            )

    def test_clock_rewind_duplicate_future_and_old_data_invalidate_mapping(self):
        api = self.api()
        for second, received in (
            (1_000_000_000, 2_020_000_000),
            (900_000_000, 2_020_000_000),
            (1_030_000_000, 2_020_000_000),
            (1_010_000_000, 2_300_000_000),
        ):
            b = self.bridge()
            b.bind_clock(
                api.ClockMapping(
                    domain="ros_system",
                    offset_ns=1_000_000_000,
                    uncertainty_ns=0,
                    valid_until_ns=3_000_000_000,
                )
            )
            b.image(image(), now_ns=2_010_000_000)
            result = b.image(image(second), now_ns=received)
            self.assertEqual(result.reason, "clock_discontinuity")
            self.assertIsNone(b.mapping)
            self.assertEqual(b.take(now_ns=received).reason, "source_waiting")

    def test_bad_image_and_clock_fields_have_fixed_faults_and_clear_latest(self):
        b = self.bridge()
        mutations = [
            image(data=b"x"),
            image(is_bigendian=True),
            image(width=True),
            image(header=header(frame="other")),
            image(0),
            image(person_id="secret"),
        ]
        for invalid in mutations:
            b.image(image(), now_ns=2_000_000_000)
            result = b.image(invalid, now_ns=2_010_000_000)
            self.assertEqual(result.reason, "sensor_invalid")
            self.assertNotIn("secret", str(result))
            self.assertEqual(b.take(now_ns=2_010_000_001).reason, "source_waiting")
        with self.assertRaises(ValueError):
            b.image(image(), now_ns=True)

    def test_pointcloud_fields_bytes_and_frame_are_preserved_without_class_inference(self):
        b = self.api().RosIngress(modality="radar", frame_id="radar/front")
        msg = {
            "header": header(frame="radar/front"),
            "height": 1,
            "width": 1,
            "fields": [
                {"name": n, "offset": i * 4, "datatype": 7, "count": 1}
                for i, n in enumerate(("x", "y", "z"))
            ],
            "is_bigendian": False,
            "point_step": 12,
            "row_step": 12,
            "is_dense": True,
            "data": array("B", struct.pack("<fff", 1, 2, 3)),
        }
        r = b.pointcloud(msg, now_ns=2_000_000_000)
        self.assertEqual(r.payload.points[0].xyz_m, (1, 2, 3))
        self.assertIsNone(r.camera)
        self.assertFalse(r.live_evidence)
        self.assertEqual(b.status(now_ns=2_000_000_001)["state"], "UNKNOWN")

    def test_source_gap_clears_pending_payload_and_restarts_scene(self):
        b = self.bridge()
        b.image(image(), now_ns=2_000_000_000)
        self.assertEqual(b.take(now_ns=2_100_000_001).reason, "source_timeout")
        r = b.image(image(1_200_000_000), now_ns=2_200_000_000)
        self.assertTrue(r.scene_break)
        self.assertEqual(b.status(now_ns=2_200_000_001)["source_state"], "receiving")

    def test_expired_intrinsics_are_removed_at_consumption_and_layout_breaks_scene(self):
        b = self.bridge()
        b.camera_info(camera(), now_ns=2_000_000_000, valid_for_ns=20_000_000)
        b.image(image(), now_ns=2_001_000_000)
        r = b.take(now_ns=2_030_000_000)
        self.assertIsNone(r.camera)
        self.assertIsNone(r.calibration_digest)
        self.assertTrue(r.scene_break)
        r = b.image(image(1_040_000_000, width=1, step=2, data=b"\x00\x00"), now_ns=2_040_000_000)
        self.assertTrue(r.scene_break)

    def test_invalid_oversized_buffers_and_nonfinite_camera_arrays_are_bounded(self):
        b = self.bridge()
        for raw in (memoryview(bytearray(8 * 1024 * 1024 + 1)), array("H", [1, 2]), object()):
            self.assertEqual(
                b.image(image(data=raw), now_ns=2_000_000_000).reason, "sensor_invalid"
            )
        for change in ({"k": [float("nan")] * 9}, {"d": [0.0] * 100}, {"p": [10**400] * 12}):
            self.assertEqual(
                b.camera_info(camera(**change), now_ns=2_000_000_000).reason, "calibration_invalid"
            )

    def test_optional_node_validates_configuration_before_loading_ros(self):
        from aethron_edge.sensors.ros2_node import RosSubscriber

        for topic in ("relative", "/../escape", "/double//slash", "/secret?token=x"):
            with self.assertRaisesRegex(ValueError, "invalid_topic"):
                RosSubscriber(self.bridge(), topic=topic, context=None)

    def test_status_has_local_expiry_and_fixed_closed_state(self):
        b = self.bridge()
        status = b.status(now_ns=2_000_000_000)
        self.assertEqual(status["emitted_ns"], 2_000_000_000)
        self.assertEqual(status["expires_ns"], 2_100_000_000)

    def test_mapping_expired_before_consumption_withdraws_capture_time(self):
        b = self.bridge()
        b.bind_clock(
            self.api().ClockMapping(
                domain="ros_system",
                offset_ns=1_000_000_000,
                uncertainty_ns=0,
                valid_until_ns=2_020_000_000,
            )
        )
        b.image(image(), now_ns=2_010_000_000)
        result = b.take(now_ns=2_030_000_000)
        self.assertIsNone(result.capture_ns)
        self.assertIsNone(b.mapping)
        self.assertTrue(result.scene_break)

    def test_2000_malformed_ros_packets_fail_without_input_echo(self):
        import random

        from aethron_edge.sources.base import SourceFault

        rng = random.Random(20261009)
        values = [None, True, -1, 10**400, float("nan"), "secret", [], {"person_id": "secret"}]
        fields = ["header", "height", "width", "encoding", "is_bigendian", "step", "data"]
        b = self.bridge()
        rejected = 0
        for _ in range(2000):
            value = image()
            value[rng.choice(fields)] = rng.choice(values)
            result = b.image(value, now_ns=2_000_000_000)
            if isinstance(result, SourceFault):
                rejected += 1
                self.assertNotIn("secret", str(result))
            else:
                self.assertFalse(result.live_evidence)
        self.assertEqual(rejected, 2000)
