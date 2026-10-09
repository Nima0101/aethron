"""Real ROS Jazzy DDS with original synthetic payloads, never hardware commands."""

import importlib.util
import math
import struct
import time
import unittest
from array import array

from rclpy.context import Context
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, Image, PointCloud2, PointField


class InstalledDDS(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("aethron_edge.sensors.ros2_node"),
            "installed ROS subscriber missing",
        )
        from aethron_edge.sensors.ros2 import RosIngress
        from aethron_edge.sensors.ros2_node import RosSubscriber

        self.context = Context()
        self.context.init(args=[], domain_id=173)
        self.publisher = Node(
            "aethron_synthetic_fixture",
            context=self.context,
            enable_rosout=False,
            start_parameter_services=False,
        )
        self.qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.bridge = RosIngress(modality="depth", frame_id="front_optical", meters_per_unit=0.002)
        self.subscriber = RosSubscriber(
            self.bridge,
            topic="/aethron_test/depth",
            camera_info_topic="/aethron_test/info",
            context=self.context,
        )

    def tearDown(self):
        if hasattr(self, "subscriber"):
            self.subscriber.close()
            self.publisher.destroy_node()
            self.context.shutdown()

    def connected(self, publisher, subscriber):
        until = time.monotonic() + 10
        while publisher.get_subscription_count() < 1 and time.monotonic() < until:
            subscriber.poll(timeout_sec=0.01)
        self.assertEqual(publisher.get_subscription_count(), 1)

    def deliver(self, publisher, message, subscriber, predicate):
        until = time.monotonic() + 5
        while time.monotonic() < until:
            publisher.publish(message)
            result = subscriber.poll(timeout_sec=0.02)
            if predicate(result):
                return result
        self.fail("DDS message not accepted within test deadline")

    def test_real_image_camera_info_and_loss(self):
        info_pub = self.publisher.create_publisher(CameraInfo, "/aethron_test/info", self.qos)
        image_pub = self.publisher.create_publisher(Image, "/aethron_test/depth", self.qos)
        self.connected(info_pub, self.subscriber)
        self.connected(image_pub, self.subscriber)
        info = CameraInfo()
        info.header.frame_id = "front_optical"
        info.width = 2
        info.height = 1
        info.distortion_model = "plumb_bob"
        info.d = [0.0] * 5
        info.k = [2.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 1.0]
        info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        info.p = [2.0, 0.0, 0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        self.deliver(info_pub, info, self.subscriber, lambda _: self.bridge.calibration is not None)
        message = Image()
        message.header.frame_id = "front_optical"
        message.header.stamp.sec = 1
        message.width = 2
        message.height = 1
        message.step = 4
        message.encoding = "16UC1"
        message.data = array("B", struct.pack("<HH", 0, 2500))
        result = self.deliver(image_pub, message, self.subscriber, lambda r: hasattr(r, "payload"))
        self.assertEqual(result.payload.depth_m(1, 0), 5)
        self.assertIsNotNone(result.camera)
        self.assertFalse(result.live_evidence)
        self.assertIsNone(result.capture_ns)
        # Node creates no command publisher. rclpy's own parameter event topic is explicit.
        self.assertTrue(
            all(
                name == "/parameter_events"
                for name, _ in self.subscriber.node.get_publisher_names_and_types_by_node(
                    self.subscriber.node.get_name(), "/"
                )
            )
        )
        time.sleep(0.12)
        self.assertEqual(self.bridge.status(now_ns=time.monotonic_ns())["source_state"], "lost")
        self.assertEqual(self.bridge.status(now_ns=time.monotonic_ns())["state"], "UNKNOWN")

    def test_real_pointcloud_and_closed_unsubscribe(self):
        from aethron_edge.sensors.ros2 import RosIngress
        from aethron_edge.sensors.ros2_node import RosSubscriber

        bridge = RosIngress(modality="radar", frame_id="radar/front")
        subscriber = RosSubscriber(bridge, topic="/aethron_test/radar", context=self.context)
        try:
            publisher = self.publisher.create_publisher(
                PointCloud2, "/aethron_test/radar", self.qos
            )
            self.connected(publisher, subscriber)
            message = PointCloud2()
            message.header.frame_id = "radar/front"
            message.header.stamp.sec = 1
            message.height = 1
            message.width = 1
            message.point_step = 12
            message.row_step = 12
            message.fields = [
                PointField(name=n, offset=i * 4, datatype=PointField.FLOAT32, count=1)
                for i, n in enumerate(("x", "y", "z"))
            ]
            message.data = array("B", struct.pack("<fff", 1, 2, 3))
            message.is_dense = True
            result = self.deliver(publisher, message, subscriber, lambda r: hasattr(r, "payload"))
            self.assertEqual(result.payload.points[0].xyz_m, (1.0, 2.0, 3.0))
            self.assertFalse(result.live_evidence)
        finally:
            subscriber.close()
        self.assertEqual(subscriber.poll(timeout_sec=0).reason, "source_closed")

    def test_malformed_dds_image_withdraws_source_and_recovers(self):
        publisher = self.publisher.create_publisher(Image, "/aethron_test/depth", self.qos)
        self.connected(publisher, self.subscriber)
        message = Image()
        message.header.frame_id = "front_optical"
        message.header.stamp.sec = 1
        message.height = 1
        message.width = 2
        message.step = 1
        message.encoding = "16UC1"
        message.data = array("B", bytes(4))
        self.deliver(
            publisher, message, self.subscriber, lambda _: self.bridge.fault == "sensor_invalid"
        )
        self.assertIsNone(self.bridge.latest)
        self.assertEqual(self.bridge.status(now_ns=time.monotonic_ns())["state"], "UNKNOWN")
        message.step = 4
        message.header.stamp.sec = 2
        result = self.deliver(publisher, message, self.subscriber, lambda r: hasattr(r, "payload"))
        self.assertTrue(result.scene_break)
        self.assertFalse(result.live_evidence)

    def test_installed_dds_geometry_provider(self):
        from aethron_edge.sensors.geometry import Pinhole
        from aethron_edge.sensors.packets import CloudLayout
        from aethron_edge.sensors.provider import (
            GeometryProvider,
            ProviderCalibration,
            layout_digest,
        )
        from aethron_edge.sensors.registration import RigCalibration
        from aethron_edge.sensors.ros2 import ClockMapping, RosIngress
        from aethron_edge.sensors.ros2_node import RosSubscriber

        layout = CloudLayout(
            width=1,
            height=1,
            point_step=12,
            row_step=12,
            is_bigendian=False,
            fields=[
                {"name": n, "offset": i * 4, "datatype": 7, "count": 1}
                for i, n in enumerate(("x", "y", "z"))
            ],
        )
        rig = RigCalibration(
            version=1,
            source_frame="radar/front",
            target_frame="front_optical",
            mount_id="rig_a",
            evidence="synthetic",
            camera=Pinhole(width=640, height=480, fx=400.0, fy=400.0, cx=320.0, cy=240.0),
            rotation=(1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0),
            translation_m=(0.5, 0.0, 0.0),
            translation_error_m=0.01,
            rotation_error_rad=0.0,
            reprojection_error_px=0.0,
        )
        calibration = ProviderCalibration(
            source_id="radar_front",
            modality="radar",
            rig=rig,
            source_camera=None,
            measurement_error_m=0.01,
            layout_sha256=layout_digest(layout),
        )
        provider = GeometryProvider(
            calibration, mode="ros", clock_id="fixture_boot", valid_for_ns=10_000_000_000
        )
        bridge = RosIngress(modality="radar", frame_id="radar/front")
        subscriber = RosSubscriber(bridge, topic="/aethron_test/registered", context=self.context)
        try:
            publisher = self.publisher.create_publisher(
                PointCloud2, "/aethron_test/registered", self.qos
            )
            self.connected(publisher, subscriber)
            bridge.bind_clock(
                ClockMapping(
                    domain="ros_system",
                    offset_ns=0,
                    uncertainty_ns=0,
                    valid_until_ns=time.monotonic_ns() + 5_000_000_000,
                )
            )
            message = PointCloud2()
            message.header.frame_id = "radar/front"
            message.width = 1
            message.height = 1
            message.point_step = 12
            message.row_step = 12
            message.fields = [
                PointField(name=n, offset=i * 4, datatype=7, count=1)
                for i, n in enumerate(("x", "y", "z"))
            ]
            message.data = array("B", struct.pack("<fff", 0.0, 0.0, 5.0))
            until = time.monotonic() + 5
            while time.monotonic() < until:
                stamp = time.monotonic_ns()
                message.header.stamp.sec = stamp // 1_000_000_000
                message.header.stamp.nanosec = stamp % 1_000_000_000
                publisher.publish(message)
                result = subscriber.poll_geometry(provider, [0], mount_id="rig_a", timeout_sec=0.01)
                if hasattr(result, "points"):
                    break
            self.assertEqual(result.points[0].pixel, (360.0, 240.0))
            self.assertFalse(result.live_evidence)
            self.assertEqual(provider.status()["state"], "UNKNOWN")
            subscriber.close()
            self.assertEqual(
                subscriber.poll_geometry(provider, [0], mount_id="rig_a").reason, "source_closed"
            )
            self.assertFalse(provider.status()["geometry_available"])
        finally:
            subscriber.close()
            provider.close()

    def test_raw_fisheye_dds_correction_metadata_loss_and_expiry(self):
        from aethron_edge.sensors.provider import GeometryProvider
        from aethron_edge.sensors.ros2 import ClockMapping, RosIngress
        from aethron_edge.sensors.ros2_node import RosSubscriber
        from test_ros_lens_rectification import RosLensBinding

        fixture = RosLensBinding()
        fixture.setup_path()
        bridge = RosIngress(
            modality="depth",
            frame_id="depth_optical",
            meters_per_unit=0.001,
            raw_depth_lens=fixture.lens,
        )
        provider = GeometryProvider(
            fixture.fixture.config(lens=fixture.lens),
            mode="ros",
            clock_id="dds_fixture",
            valid_for_ns=10_000_000_000,
        )
        subscriber = RosSubscriber(
            bridge,
            topic="/aethron_test/raw_depth",
            camera_info_topic="/aethron_test/raw_info",
            context=self.context,
        )
        try:
            images = self.publisher.create_publisher(Image, "/aethron_test/raw_depth", self.qos)
            infos = self.publisher.create_publisher(CameraInfo, "/aethron_test/raw_info", self.qos)
            self.connected(images, subscriber)
            self.connected(infos, subscriber)
            deadline = time.monotonic_ns() + 5_000_000_000
            bridge.bind_clock(
                ClockMapping(
                    domain="ros_system", offset_ns=0, uncertainty_ns=0, valid_until_ns=deadline
                )
            )
            info = CameraInfo()
            info.header.frame_id = "depth_optical"
            for name in ("width", "height", "distortion_model", "d", "k", "r", "p"):
                setattr(info, name, fixture.info[name])
            frame = Image()
            frame.header.frame_id = "depth_optical"
            frame.width = frame.height = 3
            frame.step = 6
            frame.encoding = "16UC1"
            frame.data = array("B", struct.pack("<9H", *([5000] * 9)))

            def observe():
                until = time.monotonic() + 5
                while time.monotonic() < until:
                    stamp = time.monotonic_ns()
                    frame.header.stamp.sec = stamp // 1_000_000_000
                    frame.header.stamp.nanosec = stamp % 1_000_000_000
                    infos.publish(info)
                    images.publish(frame)
                    result = subscriber.poll_geometry(
                        provider, [(2, 1)], mount_id="rig_a", timeout_sec=0.01
                    )
                    if getattr(result, "points", None):
                        return result
                self.fail("raw depth geometry not admitted before existing 5s DDS deadline")

            result = observe()
            self.assertAlmostEqual(result.points[0].camera_xyz_m[0], 5 * math.tan(0.5) + 0.5)
            self.assertFalse(result.live_evidence)
            self.assertEqual(result.source_evidence, "external_unverified")
            self.assertLessEqual(result.expires_ns, deadline)
            self.assertLessEqual(result.expires_ns, result.capture_ns + 100_000_000)
            info.d = [0.001, 0.0, 0.0, 0.0]
            self.deliver(infos, info, subscriber, lambda _: bridge.fault == "calibration_invalid")
            self.assertFalse(provider.status()["geometry_available"])
            info.d = [0.0] * 4
            self.assertTrue(observe().scene_break)
            time.sleep(0.12)
            self.assertFalse(provider.status()["geometry_available"])
        finally:
            subscriber.close()
            provider.close()

    def test_headless_installed_cli_exits_cleanly_on_sigterm(self):
        import json
        import select
        import subprocess
        import sys

        import aethron_edge

        self.assertTrue(aethron_edge.__file__.startswith("/tmp/aethron-ros/"))
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "aethron_edge.sensors.ros2_node",
                "--modality",
                "depth",
                "--topic",
                "/aethron_test/empty",
                "--frame-id",
                "front_optical",
                "--meters-per-unit",
                "0.002",
                "--domain-id",
                "174",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertTrue(select.select([process.stdout], [], [], 10)[0], "no autonomous status")
            row = json.loads(process.stdout.readline())
            self.assertEqual(row["state"], "UNKNOWN")
            self.assertFalse(row["qualified"])
            process.terminate()
            process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class InstalledRosAppliance(unittest.TestCase):
    def test_renewal_loss_expiry_reaps_without_revival(self):
        import tempfile
        from pathlib import Path

        from aethron_edge.config import load_config
        from aethron_edge.runtime.supervisor import ApplianceSupervisor
        from test_sensor_ros_appliance import fixture
        from test_signed_service import publisher

        supervisor = ApplianceSupervisor()
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = fixture(
                Path(tmp), valid_for_ns=4_000_000_000, version=2, renewal="software_fixture"
            )
            try:
                with publisher():
                    supervisor.boot(load_config(path))
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        with supervisor.lock:
                            pipeline = supervisor.pipelines["depth"]
                            if (
                                pipeline.ros_grant.generation >= 2
                                and pipeline.sensor_status(time.monotonic_ns())["available"]
                            ):
                                break
                        time.sleep(0.01)
                    self.assertGreaterEqual(
                        pipeline.ros_grant.generation,
                        2,
                        pipeline.sensor_status(time.monotonic_ns()),
                    )
                    self.assertTrue(pipeline.sensor_status(time.monotonic_ns())["available"])
                    self.assertEqual(supervisor.status(time.monotonic_ns())["restarts"], 0)
                # No source, viewer or external issuer can keep this grant alive.
                deadline = time.monotonic() + 6
                while not pipeline.ros_guard.closed and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(pipeline.ros_guard.closed)
                self.assertFalse(pipeline.sensor_status(time.monotonic_ns())["available"])
                generation = pipeline.ros_grant.generation
                with publisher():
                    deadline = time.monotonic() + 5
                    while pipeline.process is not None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    with supervisor.lock:
                        self.assertIsNone(pipeline.process)
                        self.assertIs(supervisor.pipelines["depth"], pipeline)
                        self.assertIn("depth", supervisor.faults)
                        self.assertEqual(supervisor.status(time.monotonic_ns())["restarts"], 0)
                        self.assertEqual(pipeline.ros_grant.generation, generation)
                        self.assertTrue(pipeline.ros_guard.closed)
                        self.assertFalse(pipeline.sensor_status(time.monotonic_ns())["available"])
                        self.assertEqual(
                            pipeline.sensor_status(time.monotonic_ns())["state"], "fault"
                        )
                        self.assertEqual(pipeline.snapshot(time.monotonic_ns())["state"], "UNKNOWN")
            finally:
                supervisor.shutdown()

    def test_supervisor_without_viewers_loss_restart_and_bounded_authority(self):
        import json
        import tempfile
        from pathlib import Path

        from aethron_edge.config import load_config
        from aethron_edge.runtime.supervisor import ApplianceSupervisor
        from test_sensor_ros_appliance import fixture

        context = Context()
        context.init(args=[], domain_id=73)
        publisher = Node(
            "aethron_appliance_fixture",
            context=context,
            enable_rosout=False,
            start_parameter_services=False,
        )
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        info_pub = publisher.create_publisher(CameraInfo, "/aethron/camera_info", qos)
        image_pub = publisher.create_publisher(Image, "/aethron/depth", qos)
        info = CameraInfo()
        info.header.frame_id = "depth_optical"
        info.width = info.height = 3
        info.distortion_model = "plumb_bob"
        info.d = [0.0] * 5
        info.k = [2.0, 0.0, 1.0, 0.0, 2.0, 1.0, 0.0, 0.0, 1.0]
        info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        info.p = [2.0, 0.0, 1.0, 0.0, 0.0, 2.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        message = Image()
        message.header.frame_id = "depth_optical"
        message.width = message.height = 3
        message.encoding = "16UC1"
        message.step = 6
        message.data = array("B", struct.pack("<9H", *([5000] * 9)))
        supervisor = ApplianceSupervisor()

        def publish_until(predicate, timeout=10):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                # Original software fixture, with explicit system-time timestamps.
                stamp = time.time_ns() - 5_000_000
                message.header.stamp.sec = stamp // 1_000_000_000
                message.header.stamp.nanosec = stamp % 1_000_000_000
                info_pub.publish(info)
                image_pub.publish(message)
                if predicate():
                    return
                time.sleep(0.01)
            self.fail("supervised ROS did not satisfy condition within deadline")

        try:
            with tempfile.TemporaryDirectory() as tmp:
                path, manifest = fixture(Path(tmp))
                supervisor.boot(load_config(path))
                publish_until(
                    lambda: (
                        supervisor.status(time.monotonic_ns())["sensors"]["depth"]["batches"] >= 3
                    )
                )
                pipeline = supervisor.pipelines["depth"]
                grant = pipeline.ros_grant
                self.assertEqual(pipeline.inferences, 0)
                self.assertEqual(pipeline.snapshot(time.monotonic_ns())["state"], "UNKNOWN")
                self.assertFalse(supervisor.status(time.monotonic_ns())["qualified"])
                before = pipeline.sensor_batches
                time.sleep(0.15)  # No publisher or API viewer; independent parent expiry.
                self.assertFalse(
                    supervisor.status(time.monotonic_ns())["sensors"]["depth"]["available"]
                )
                publish_until(lambda: supervisor.pipelines["depth"].sensor_batches > before)
                pipeline.process.terminate()  # Only this test's child, never another session.
                publish_until(
                    lambda: (
                        supervisor.pipelines["depth"] is not pipeline
                        and supervisor.pipelines["depth"].sensor_batches > before + 1
                    )
                )
                self.assertEqual(supervisor.pipelines["depth"].ros_grant, grant)
                self.assertEqual(
                    supervisor.status(time.monotonic_ns())["sensors"]["depth"]["source_evidence"],
                    "external_unverified",
                )
                # Signed/static manifest identity is pinned by boot grant; mutation
                # on worker replacement cannot mint a new authority.
                changed = manifest.model_dump(mode="json")
                changed["timestamp_error_ns"] += 1
                (Path(tmp) / "sensor.json").write_text(json.dumps(changed))
                current = supervisor.pipelines["depth"]
                current.process.terminate()
                deadline = time.monotonic() + 5
                while supervisor.pipelines["depth"] is current and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertIsNot(supervisor.pipelines["depth"], current)
                time.sleep(0.2)
                self.assertFalse(
                    supervisor.status(time.monotonic_ns())["sensors"]["depth"]["available"]
                )
        finally:
            supervisor.shutdown()
            publisher.destroy_node()
            context.shutdown()
