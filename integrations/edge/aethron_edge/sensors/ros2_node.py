"""Optional ROS Jazzy subscriber and local status process; no command publishers.

rclpy is installed by the ROS distribution, not implicitly fetched by pip.
Use a dedicated constrained process and authenticated/isolated DDS transport.
"""

import argparse
import hashlib
import json
import signal
import threading
import time

from ..sources.base import SourceFault
from .ros2 import RosIngress, _frame


def _topic(value):
    if type(value) is not str or not value.startswith("/"):
        raise ValueError("invalid_topic")
    try:
        _frame(value[1:])
    except ValueError:
        raise ValueError("invalid_topic") from None
    return value


class RosSubscriber:
    """Caller owns the Context; this instance owns only its node and executor."""

    def __init__(self, bridge: RosIngress, *, topic, context, camera_info_topic=None):
        if not isinstance(bridge, RosIngress):
            raise ValueError("invalid_ingress")
        _topic(topic)
        cloud = bridge.modality in {"radar", "lidar"}
        if camera_info_topic is not None:
            _topic(camera_info_topic)
            if cloud or camera_info_topic == topic:
                raise ValueError("invalid_camera_topic")
        try:
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.node import Node
            from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
            from sensor_msgs.msg import CameraInfo, Image, PointCloud2
        except ImportError:
            raise RuntimeError("ros2_unavailable") from None
        self.bridge = bridge
        self.closed = False
        name = "aethron_sensor_" + hashlib.sha256(topic.encode()).hexdigest()[:12]
        self.node = Node(
            name,
            context=context,
            use_global_arguments=False,
            enable_rosout=False,
            start_parameter_services=False,
            enable_logger_service=False,
        )
        self.executor = SingleThreadedExecutor(context=context)
        try:
            qos = QoSProfile(
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE,
            )
            callback = bridge.pointcloud if cloud else bridge.image
            self.node.create_subscription(
                PointCloud2 if cloud else Image,
                topic,
                lambda msg: callback(msg, now_ns=time.monotonic_ns()),
                qos,
            )
            if camera_info_topic is not None:
                self.node.create_subscription(
                    CameraInfo,
                    camera_info_topic,
                    lambda msg: bridge.camera_info(msg, now_ns=time.monotonic_ns()),
                    qos,
                )
            self.executor.add_node(self.node)
        except Exception:
            self.close()
            raise

    def _spin(self, timeout_sec):
        if type(timeout_sec) not in (int, float) or not 0 <= timeout_sec <= 0.1:
            raise ValueError("invalid_poll_timeout")
        if self.closed:
            return False
        self.executor.spin_once(timeout_sec=float(timeout_sec))
        return True

    def poll(self, *, timeout_sec=0.05):
        if not self._spin(timeout_sec):
            return SourceFault("source_closed")
        return self.bridge.take(now_ns=time.monotonic_ns())

    def poll_geometry(self, provider, indices, *, mount_id, timeout_sec=0.05):
        """Consume once through calibration admission, rather than raw poll()."""
        from .provider import GeometryProvider

        if not isinstance(provider, GeometryProvider):
            raise ValueError("invalid_provider")
        if not self._spin(timeout_sec):
            provider.source_lost()
            return SourceFault("source_closed")
        return provider.ros(self.bridge, indices, mount_id=mount_id)

    def close(self):
        if not self.closed:
            self.closed = True
            self.executor.remove_node(self.node)
            self.executor.shutdown(timeout_sec=1.0)
            self.node.destroy_node()
            self.bridge.latest = None
            self.bridge.calibration = None
            self.bridge.mapping = None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--modality", choices=["lwir", "nir", "depth", "radar", "lidar"], required=True
    )
    parser.add_argument("--topic", required=True)
    parser.add_argument("--camera-info-topic")
    parser.add_argument("--frame-id", required=True)
    parser.add_argument("--meters-per-unit", type=float)
    parser.add_argument("--domain-id", type=int, default=0)
    parser.add_argument(
        "--duration", type=float, help="Finite diagnostic duration; default runs continuously"
    )
    args = parser.parse_args()
    if not 0 <= args.domain_id <= 232 or (
        args.duration is not None and not 0 < args.duration <= 3600
    ):
        parser.error("invalid_runtime_limit")
    context = subscriber = None
    stop = threading.Event()
    previous_term = signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        bridge = RosIngress(
            modality=args.modality, frame_id=args.frame_id, meters_per_unit=args.meters_per_unit
        )
        _topic(args.topic)
        if args.camera_info_topic is not None:
            _topic(args.camera_info_topic)
        from rclpy.context import Context

        context = Context()
        context.init(args=[], domain_id=args.domain_id)
        subscriber = RosSubscriber(
            bridge, topic=args.topic, context=context, camera_info_topic=args.camera_info_topic
        )
        start = time.monotonic()
        next_status = start
        while (
            not stop.is_set()
            and context.ok()
            and (args.duration is None or time.monotonic() - start < args.duration)
        ):
            subscriber.poll()
            if time.monotonic() >= next_status:
                print(
                    json.dumps(bridge.status(now_ns=time.monotonic_ns()), sort_keys=True),
                    flush=True,
                )
                next_status = time.monotonic() + 1
    except KeyboardInterrupt:
        pass
    except (ImportError, RuntimeError, ValueError):
        parser.exit(2, "ros_sensor_startup_failed\n")
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        if subscriber is not None:
            subscriber.close()
        if context is not None and context.ok():
            context.shutdown()


if __name__ == "__main__":
    main()
