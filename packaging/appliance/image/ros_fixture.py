"""Guest-only analytical depth publisher; no devices, subscriptions or control topics."""

import os
import struct
import threading
import time
from array import array


class DepthFixture:
    def __init__(self, *, domain_id, topic, camera_info_topic):
        from rclpy.context import Context
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import CameraInfo, Image

        os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "LOCALHOST"
        os.environ["ROS_LOCALHOST_ONLY"] = "1"
        self.context = Context()
        self.context.init(args=[], domain_id=domain_id)
        self.node = Node(
            "aethron_guest_fixture",
            context=self.context,
            enable_rosout=False,
            start_parameter_services=False,
        )
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.images = self.node.create_publisher(Image, topic, qos)
        self.infos = self.node.create_publisher(CameraInfo, camera_info_topic, qos)
        self.info = CameraInfo()
        self.info.header.frame_id = "depth_optical"
        self.info.width = self.info.height = 3
        self.info.distortion_model = "plumb_bob"
        self.info.d = [0.0] * 5
        self.info.k = [2.0, 0.0, 1.0, 0.0, 2.0, 1.0, 0.0, 0.0, 1.0]
        self.info.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        self.info.p = [2.0, 0.0, 1.0, 0.0, 0.0, 2.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
        self.frame = Image()
        self.frame.header.frame_id = "depth_optical"
        self.frame.width = self.frame.height = 3
        self.frame.encoding = "16UC1"
        self.frame.step = 6
        self.frame.data = array("B", struct.pack("<9H", *([5000] * 9)))
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.mode = "publish"
        self.failed = False
        self.thread = threading.Thread(target=self._work, name="aethron-guest-depth", daemon=True)

    def set_mode(self, mode):
        if mode not in {"publish", "pause", "rewind"}:
            raise ValueError("invalid_fixture_mode")
        with self.lock:
            self.mode = mode

    def _work(self):
        try:
            while not self.stop.is_set():
                with self.lock:
                    mode = self.mode
                if mode != "pause":
                    stamp = time.time_ns() - 5_000_000 - (1_000_000_000 if mode == "rewind" else 0)
                    self.frame.header.stamp.sec = stamp // 1_000_000_000
                    self.frame.header.stamp.nanosec = stamp % 1_000_000_000
                    self.infos.publish(self.info)
                    self.images.publish(self.frame)
                self.stop.wait(0.02)
        except Exception:
            self.failed = True

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=2)
        self.node.destroy_node()
        self.context.shutdown()
        if self.thread.is_alive() or self.failed:
            raise RuntimeError("fixture_publisher_failed")
