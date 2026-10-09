"""Bounded depth/cloud geometry provider; no semantic or live-evidence promotion.

A process owns a provider and its clock. Recorded logical clocks and ROS host
monotonic clocks are separate modes. No raw payload or point history is retained.
"""

import hashlib
import json
import time
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import Field, model_validator

from ..sources.base import SourceFault
from .geometry import Pinhole
from .packets import Closed, Cloud, Raster, layout_digest
from .rectification import FisheyeCalibration, LensCalibration
from .registration import AGE_NS, RegisteredPoint, Registration, RigCalibration, _ns
from .replay import RecordedFrame
from .ros2 import RosIngress


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


class ProviderCalibration(Closed):
    source_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    modality: Literal["depth", "radar", "lidar"]
    rig: RigCalibration
    source_camera: Pinhole | None
    lens: LensCalibration | FisheyeCalibration | None = None
    measurement_error_m: float = Field(ge=0, le=10)
    layout_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def geometry(self):
        if self.modality == "depth":
            if self.source_camera is None or (
                self.lens is not None and self.lens.camera != self.source_camera
            ):
                raise ValueError("invalid_depth_calibration")
        elif self.source_camera is not None or self.lens is not None:
            raise ValueError("unexpected_camera_calibration")
        return self

    @property
    def digest(self):
        return _digest(self.model_dump())


@dataclass(frozen=True)
class GeometryBatch:
    points: tuple[RegisteredPoint, ...]
    invalid_samples: int
    source_evidence: Literal["recorded", "external_unverified"]
    calibration_digest: str
    capture_ns: int
    expires_ns: int
    scene_break: bool

    @property
    def live_evidence(self):
        return False


class GeometryProvider:
    """Single executor, at most 64 selected points; lifetime is never auto-renewed."""

    def __init__(self, calibration, *, mode, clock_id, valid_for_ns, clock=time.monotonic_ns):
        if not isinstance(calibration, ProviderCalibration) or mode not in {"recorded", "ros"}:
            raise ValueError("invalid_provider")
        if not callable(clock):
            raise ValueError("invalid_clock")
        self.calibration = calibration
        self.mode = mode
        self.clock = clock
        self.binding = Registration(
            calibration.rig, now_ns=clock(), valid_for_ns=valid_for_ns, clock_id=clock_id
        )
        self.last_now = self.binding.last_now
        self.last_stamp = self.last_sequence = None
        self.expires = None
        self.pending_break = True
        self.ingress = None
        self.context = None

    def close(self):
        self.binding.close()
        self.source_lost()

    def source_lost(self):
        self.expires = None
        self.pending_break = True

    def _fault(self):
        self.source_lost()
        return SourceFault("provider_unavailable")

    def _now(self):
        try:
            now = _ns(self.clock())
        except (ValueError, TypeError, OverflowError):
            self.close()
            raise ValueError("invalid_clock") from None
        if now < self.last_now:
            self.close()
        self.last_now = now
        if self.binding.closed or now > self.binding.valid_until:
            raise ValueError("expired_binding")
        return now

    def _context(self):
        b = self.ingress
        # Matching CameraInfo can refresh its lease, but never the expiry of an
        # already projected result. Packet format changes also invalidate old geometry
        # before the next provider poll. Identity and current expiry are checked separately.
        return (
            None
            if b is None
            else (b.mapping, b.last_layout, None if b.calibration is None else b.calibration[:2])
        )

    def status(self):
        try:
            now = self._now()
            available = self.expires is not None and now <= self.expires
            if self.ingress is not None and (self.ingress.fault or self.context != self._context()):
                available = False
            if (
                self.ingress is not None
                and self.ingress.calibration is not None
                and now > self.ingress.calibration[2]
            ):
                available = False
            if not available:
                self.source_lost()
        except (ValueError, TypeError, OverflowError):
            self.close()
            available = False
        return {"state": "UNKNOWN", "geometry_available": available, "qualified": False}

    def _mount(self, mount_id):
        if mount_id != self.calibration.rig.mount_id:
            self.close()
            raise ValueError("changed_mount")

    def recorded(self, frame, indices, *, mount_id):
        try:
            now = self._now()
            self._mount(mount_id)
            c = self.calibration
            if self.mode != "recorded" or not isinstance(frame, RecordedFrame):
                raise ValueError("wrong_mode")
            h = frame.header
            if (
                h.source_id != c.source_id
                or h.modality != c.modality
                or h.coordinate_frame != c.rig.source_frame
                or h.calibration_sha256 != c.digest
                or layout_digest(h.layout) != c.layout_sha256
                or (self.last_sequence is not None and h.sequence <= self.last_sequence)
            ):
                raise ValueError("recording_changed")
            result = self._project(
                frame.payload,
                indices,
                now=now,
                capture=h.acquisition_ns,
                uncertainty=h.uncertainty_ns,
                expiry=self.binding.valid_until,
                scene_break=False,
                evidence="recorded",
            )
            if not isinstance(result, SourceFault):
                self.last_sequence = h.sequence
            return result
        except (ValueError, TypeError, OverflowError, AttributeError):
            return self._fault()

    def ros(self, ingress, indices, *, mount_id):
        try:
            now = self._now()
            self._mount(mount_id)
            c = self.calibration
            if self.mode != "ros" or not isinstance(ingress, RosIngress):
                raise ValueError("wrong_mode")
            if self.ingress is None:
                self.ingress = ingress
            if ingress is not self.ingress:
                self.close()
                raise ValueError("changed_source")
            observation = ingress.take(now_ns=now)
            if (
                isinstance(observation, SourceFault)
                and observation.reason == "source_waiting"
                and self.status()["geometry_available"]
            ):
                return observation  # No duplicate batch or new evidence/expiry.
            if (
                isinstance(observation, SourceFault)
                or ingress.modality != c.modality
                or observation.frame_id != c.rig.source_frame
                or observation.capture_ns is None
                or ingress.mapping is None
            ):
                raise ValueError("unavailable_source")
            payload = observation.payload
            layout_hash = (
                layout_digest(payload.layout)
                if isinstance(payload, Raster)
                else observation.layout_sha256
            )
            if layout_hash != c.layout_sha256:
                raise ValueError("changed_layout")
            expiry = min(self.binding.valid_until, ingress.mapping.valid_until_ns)
            if isinstance(payload, Raster):
                # The raw-stream lens is configured independently of the message;
                # never reinterpret an undistorted stream or apply another model.
                if (
                    observation.raw_depth_lens != c.lens
                    or ingress.raw_depth_lens != c.lens
                    or observation.camera != c.source_camera
                    or observation.calibration_digest is None
                    or ingress.calibration is None
                    or observation.calibration_digest != ingress.calibration[1]
                    or observation.calibration_until_ns is None
                ):
                    raise ValueError("unavailable_calibration")
                expiry = min(expiry, ingress.calibration[2], observation.calibration_until_ns)
            context = self._context()
            result = self._project(
                payload,
                indices,
                now=now,
                capture=observation.capture_ns,
                uncertainty=observation.uncertainty_ns,
                expiry=expiry,
                scene_break=observation.scene_break or self.context != context,
                evidence="external_unverified",
            )
            self.context = context
            return result
        except (ValueError, TypeError, OverflowError, AttributeError):
            return self._fault()

    def _project(
        self, payload, indices, *, now, capture, uncertainty, expiry, scene_break, evidence
    ):
        try:
            _ns(capture)
            _ns(uncertainty)
            expiry = min(expiry, capture + AGE_NS - uncertainty)
            if (
                uncertainty > 50_000_000
                or capture + uncertainty > now
                or expiry < now
                or (self.last_stamp is not None and capture <= self.last_stamp)
                or not isinstance(indices, (list, tuple))
                or not 1 <= len(indices) <= 64
            ):
                raise ValueError("invalid_admission")
            c = self.calibration
            selected = []
            if isinstance(payload, Raster):
                if (
                    c.modality != "depth"
                    or type(payload.data) is not bytes
                    or len(payload.data) != payload.layout.step * payload.layout.height
                    or payload.layout.modality != "depth"
                    or (payload.layout.width, payload.layout.height)
                    != (c.source_camera.width, c.source_camera.height)
                    or layout_digest(payload.layout) != c.layout_sha256
                ):
                    raise ValueError("wrong_raster")
                for index in indices:
                    if (
                        not isinstance(index, (tuple, list))
                        or len(index) != 2
                        or any(type(i) is not int for i in index)
                    ):
                        raise ValueError("invalid_pixel")
                    selected.append(tuple(index))
                if len(set(selected)) != len(selected):
                    raise ValueError("duplicate_sample")
                depths = [payload.depth_m(u, v) for u, v in selected]
                pixels = [
                    pixel
                    for pixel, depth in zip(selected, depths, strict=True)
                    if depth is not None
                ]
                camera = c.source_camera
                if c.lens is not None:
                    # One bounded native inversion per frame, preserving selection
                    # order and unknown depths without submitting them to the solver.
                    pixels = c.lens.rectify_points(pixels)
                    camera = c.lens.output_camera
                rays = iter(pixels)
                samples = [
                    None if depth is None else camera.deproject(*next(rays), depth)
                    for depth in depths
                ]
            elif isinstance(payload, Cloud) and c.modality in {"radar", "lidar"}:
                if any(
                    type(i) is not int or not 0 <= i < len(payload.sample_points) for i in indices
                ) or len(set(indices)) != len(indices):
                    raise ValueError("invalid_indices")
                samples = [
                    None if payload.sample_points[i] is None else payload.sample_points[i].xyz_m
                    for i in indices
                ]
            else:
                raise ValueError("unsupported_geometry")
            points = []
            invalid = 0
            broken = self.pending_break or scene_break
            for sample in samples:
                if sample is None:
                    invalid += 1
                    continue
                point = self.binding.project(
                    sample,
                    measurement_error_m=c.measurement_error_m,
                    source_frame=c.rig.source_frame,
                    mount_id=c.rig.mount_id,
                    capture_ns=capture,
                    uncertainty_ns=uncertainty,
                    clock_id=self.binding.clock_id,
                    now_ns=now,
                )
                if isinstance(point, SourceFault):
                    invalid += 1
                else:
                    points.append(
                        replace(point, expires_ns=min(point.expires_ns, expiry), scene_break=broken)
                    )
            if self._now() > expiry:
                raise ValueError("processing_expired")
            self.last_stamp = capture
            self.expires = expiry if points else None
            self.pending_break = not bool(points)
            return GeometryBatch(
                tuple(points), invalid, evidence, c.digest, capture, expiry, broken
            )
        except (ValueError, TypeError, OverflowError, RuntimeError):
            return self._fault()
