"""Supervisor-owned, local DDS geometry ingress. Never sends actuator commands."""

import os
import queue
import time

from ..sources.base import SourceFault
from .provider import GeometryProvider
from .ros2 import RosIngress
from .ros2_node import RosSubscriber
from .ros_authority import BootGrant, ClockGuard, read_ros_manifest


def ros_worker(profile, grant, send, stop, control=None):
    context = subscriber = guard = provider = bridge = None
    batches = 0
    duration_ms = 0.0

    def publish(state, expires=0):
        send(
            {
                "data": None,
                "reason": None if state == "processing" else "source_lost",
                "latency_ms": duration_ms,
                "sensor_state": state,
                "sensor_batches": batches,
                "sensor_expires_ns": expires,
                "sensor_emitted_ns": time.monotonic_ns(),
                "sensor_generation": grant.generation,
                "sensor_fault": (guard.fault if guard and guard.fault else "worker_fault")
                if state == "fault"
                else None,
            }
        )

    try:
        manifest = read_ros_manifest(profile)
        guard = ClockGuard(grant, manifest, boot_id=grant.boot_id)
        bridge = RosIngress(
            modality=manifest.calibration.modality,
            frame_id=manifest.calibration.rig.source_frame,
            meters_per_unit=manifest.meters_per_unit,
            raw_depth_lens=manifest.calibration.lens,
        )
        bridge.bind_clock(guard.mapping)
        remaining = grant.valid_until_ns - time.monotonic_ns()
        provider = GeometryProvider(
            manifest.calibration,
            mode="ros",
            clock_id=grant.boot_id,
            valid_for_ns=remaining,
        )
        # This first authority supports only same-host system-time publishers.
        # DDS isolation/authentication is a separate installation prerequisite.
        os.environ["ROS_AUTOMATIC_DISCOVERY_RANGE"] = "LOCALHOST"
        os.environ["ROS_LOCALHOST_ONLY"] = "1"
        from rclpy.context import Context

        context = Context()
        context.init(args=[], domain_id=manifest.domain_id)
        subscriber = RosSubscriber(
            bridge,
            topic=manifest.topic,
            context=context,
            camera_info_topic=manifest.camera_info_topic,
        )
        while not stop.is_set() and context.ok():
            if not guard.check(ingress=bridge, provider=provider):
                break
            if control is not None:
                try:
                    command = control.get_nowait()
                except queue.Empty:
                    command = None
                if command is not None:
                    if command.get("revoke"):
                        break
                    successor = BootGrant(**command["grant"])
                    guard.accept_renewal(
                        successor, read_ros_manifest(profile), ingress=bridge, provider=provider
                    )
                    grant = successor
                    bridge.bind_clock(guard.mapping)
                    provider = GeometryProvider(
                        manifest.calibration,
                        mode="ros",
                        clock_id=grant.boot_id,
                        valid_for_ns=grant.valid_until_ns - time.monotonic_ns(),
                    )
                    publish("waiting")
            start = time.monotonic_ns()
            result = subscriber.poll_geometry(
                provider,
                manifest.indices,
                mount_id=manifest.calibration.rig.mount_id,
                timeout_sec=0.05,
            )
            duration_ms = max(0, time.monotonic_ns() - start) / 1e6
            if not guard.check(ingress=bridge, provider=provider):
                break
            if isinstance(result, SourceFault):
                if result.reason == "source_waiting" and provider.status()["geometry_available"]:
                    publish("processing", min(provider.expires, grant.valid_until_ns))
                else:
                    publish("waiting")
            else:
                batches += 1
                publish(
                    "processing",
                    min(result.expires_ns, grant.valid_until_ns) if result.points else 0,
                )
            if bridge.mapping is None:
                # Do not silently map a discontinuous source again in this worker.
                guard.close(
                    ingress=bridge,
                    provider=provider,
                    reason="source_clock_discontinuity"
                    if bridge.fault == "clock_discontinuity"
                    else "sensor_invalid",
                )
                break
        guard.close(ingress=bridge, provider=provider)
        if not stop.is_set():
            publish("fault")
            # Expired/discontinuous authority stays withdrawn; no renewal command
            # can revive it. The parent also preserves revocation across crashes.
            while not stop.wait(0.1):
                publish("fault")
    except Exception:
        publish("fault")  # No exception details, raw samples or paths on status/API.
    finally:
        if guard is not None:
            guard.close(ingress=bridge, provider=provider)
        if subscriber is not None:
            subscriber.close()
        if context is not None and context.ok():
            context.shutdown()
