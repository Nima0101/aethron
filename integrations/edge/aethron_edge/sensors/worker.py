"""Supervisor-owned bounded recorded geometry worker, independent of viewers."""

import time
from pathlib import Path

from ..sources.base import SourceFault
from .provider import GeometryProvider
from .provisioning import load_manifest, recording_frames, verified_recording


def replay_worker(profile, send, stop):
    batches = 0
    provider = None
    logical = consumed_at = 0
    last_duration_ms = 0.0

    def recording_clock():
        return logical + time.monotonic_ns() - consumed_at

    def publish(state, *, expires=0):
        send(
            {
                "data": None,
                "reason": "source_lost" if state in {"fault", "ended"} else None,
                "latency_ms": last_duration_ms,
                "sensor_state": state,
                "sensor_batches": batches,
                "sensor_expires_ns": expires,
                "sensor_emitted_ns": time.monotonic_ns(),
            }
        )

    try:
        manifest = load_manifest(Path(profile.sensor_manifest))
        while not stop.is_set():
            with verified_recording(Path(profile.address), manifest) as stream:
                first = None
                start = time.monotonic_ns()
                logical = 0
                consumed_at = start
                for frame in recording_frames(stream):
                    stamp = frame.header.acquisition_ns + frame.header.uncertainty_ns
                    if first is None:
                        first = stamp
                    target = start + stamp - first
                    while (delay := (target - time.monotonic_ns()) / 1e9) > 0:
                        if stop.wait(min(0.1, delay)):
                            return
                        if time.monotonic_ns() < target:
                            publish("waiting")
                    if stop.is_set():
                        return
                    consumed_at = time.monotonic_ns()
                    logical = stamp
                    if provider is None:
                        provider = GeometryProvider(
                            manifest.calibration,
                            mode="recorded",
                            clock_id="recording",
                            valid_for_ns=manifest.valid_for_ns,
                            clock=recording_clock,
                        )
                    result = provider.recorded(
                        frame, manifest.indices, mount_id=manifest.calibration.rig.mount_id
                    )
                    last_duration_ms = max(0, time.monotonic_ns() - consumed_at) / 1e6
                    if isinstance(result, SourceFault):
                        publish("fault")
                    else:
                        batches += 1
                        # This host deadline expires a diagnostic, not source evidence.
                        # The original recorded capture time never enters the core.
                        expires = consumed_at + result.expires_ns - logical if result.points else 0
                        publish("processing", expires=expires)
                provider.close()
                provider = None
            publish("ended")
            if not manifest.loop:
                while not stop.wait(0.1):
                    publish("ended")
                return
            if stop.wait(0.05):
                return
    except Exception:
        # No source paths, raw payload, calibration or exception details leave worker.
        publish("fault")
    finally:
        if provider is not None:
            provider.close()
