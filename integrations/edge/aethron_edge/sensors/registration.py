"""Rigid sensor-to-optical geometry with explicit declared error bounds.

No class inference, object identity or physical qualification. Persistent
calibration contains no reboot-surviving host-monotonic expiry; a local binding
supplies its clock domain and finite lifetime for each process/boot.
"""

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..sources.base import SourceFault
from .geometry import Pinhole, finite
from .packets import Closed

Name = Annotated[
    str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*(/[A-Za-z_][A-Za-z0-9_]*)*$", max_length=128)
]
Vec3 = tuple[float, float, float]
Mat3 = tuple[float, float, float, float, float, float, float, float, float]
MAX_NS = 2**63 - 1
AGE_NS = 100_000_000


def _point(value):
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError("invalid_point")
    finite(value)
    if math.hypot(*value) > 500:
        raise ValueError("point_outside_software_envelope")
    return value


def _ns(value):
    if type(value) is not int or not 0 <= value <= MAX_NS:
        raise ValueError("invalid_time")
    return value


class RigCalibration(Closed):
    version: int = Field(ge=1, le=1)
    source_frame: Name
    target_frame: Name
    mount_id: Name
    evidence: Literal["synthetic", "recorded", "external_unverified"]
    camera: Pinhole
    rotation: Mat3
    translation_m: Vec3
    translation_error_m: float = Field(ge=0, le=10)
    rotation_error_rad: float = Field(ge=0, le=0.1)
    reprojection_error_px: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def rigid(self):
        r = self.rotation
        finite(r)
        _point(self.translation_m)
        for i in range(3):
            for j in range(3):
                dot = sum(r[3 * i + k] * r[3 * j + k] for k in range(3))
                if abs(dot - (1 if i == j else 0)) > 1e-6:
                    raise ValueError("nonrigid_rotation")
        det = (
            r[0] * (r[4] * r[8] - r[5] * r[7])
            - r[1] * (r[3] * r[8] - r[5] * r[6])
            + r[2] * (r[3] * r[7] - r[4] * r[6])
        )
        if abs(det - 1) > 1e-6:
            raise ValueError("improper_rotation")
        return self

    def transform(self, xyz_m):
        point = _point(xyz_m)
        result = tuple(
            sum(self.rotation[3 * i + k] * point[k] for k in range(3)) + self.translation_m[i]
            for i in range(3)
        )
        return tuple(_point(result))

    def inverse(self, camera_xyz_m):
        point = _point(camera_xyz_m)
        translated = [point[k] - self.translation_m[k] for k in range(3)]
        return tuple(
            _point(
                tuple(
                    sum(self.rotation[3 * k + i] * translated[k] for k in range(3))
                    for i in range(3)
                )
            )
        )

    @property
    def digest(self):
        return hashlib.sha256(
            json.dumps(
                self.model_dump(), sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()


def load_calibration(raw: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= 16384:
            raise ValueError("size")
        # Check duplicate keys before Pydantic's strict JSON tuple conversion.
        json.loads(raw, object_pairs_hook=unique)
        return RigCalibration.model_validate_json(raw)
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise ValueError("invalid_calibration") from None


@dataclass(frozen=True)
class RegisteredPoint:
    camera_xyz_m: Vec3
    pixel: tuple[float, float]
    normalized: tuple[float, float]
    pixel_bounds: tuple[float, float, float, float]
    radius_m: float
    range_m: float
    target_frame: str
    calibration_digest: str
    expires_ns: int
    scene_break: bool

    @property
    def live_evidence(self):
        return False


class Registration:
    """Thread-confined binding. Error bounds are declared, never calibrated here."""

    def __init__(self, calibration, *, now_ns, valid_for_ns, clock_id):
        if not isinstance(calibration, RigCalibration):
            raise ValueError("invalid_calibration")
        try:
            # Frozen models can still be created by unchecked model_copy or
            # model_construct. Rebuild nested fields before granting a binding.
            calibration = RigCalibration.model_validate(calibration.model_dump(warnings=False))
        except (ValueError, TypeError, AttributeError, RecursionError, OverflowError):
            raise ValueError("invalid_calibration") from None
        _ns(now_ns)
        _ns(valid_for_ns)
        if not 0 < valid_for_ns <= 600_000_000_000 or now_ns + valid_for_ns > MAX_NS:
            raise ValueError("invalid_validity")
        if type(clock_id) is not str or not 1 <= len(clock_id) <= 128:
            raise ValueError("invalid_clock_domain")
        self._calibration = calibration
        self._calibration_digest = calibration.digest
        self.clock_id = clock_id
        self.valid_until = now_ns + valid_for_ns
        self.last_now = now_ns
        self.closed = False
        self.pending_break = True

    @property
    def calibration(self):
        """Validated snapshot; changing calibration requires a fresh binding."""
        return self._calibration

    def close(self):
        self.closed = True
        self.pending_break = True

    def project(
        self,
        xyz_m,
        *,
        measurement_error_m,
        source_frame,
        mount_id,
        capture_ns,
        uncertainty_ns,
        clock_id,
        now_ns,
    ):
        try:
            _ns(now_ns)
            _ns(capture_ns)
            _ns(uncertainty_ns)
            if now_ns < self.last_now:
                self.close()
            self.last_now = now_ns
            c = self.calibration
            if (
                self.closed
                or now_ns > self.valid_until
                or source_frame != c.source_frame
                or mount_id != c.mount_id
                or clock_id != self.clock_id
                or uncertainty_ns > 50_000_000
                or capture_ns + uncertainty_ns > now_ns
                or now_ns - capture_ns + uncertainty_ns > AGE_NS
            ):
                raise ValueError("invalid_registration_context")
            finite((measurement_error_m,))
            if not 0 <= measurement_error_m <= 10:
                raise ValueError("invalid_measurement_bound")
            point = _point(xyz_m)
            x, y, z = c.transform(point)
            radius = (
                measurement_error_m
                + c.translation_error_m
                + 2 * math.sin(c.rotation_error_rad / 2) * math.hypot(*point)
            )
            if z - radius <= 1e-6:
                raise ValueError("uncertainty_crosses_camera_plane")
            pixel = c.camera.project((x, y, z))
            bounds = []
            for v, f, origin in ((x, c.camera.fx, c.camera.cx), (y, c.camera.fy, c.camera.cy)):
                edges = [
                    f * a / b + origin
                    for a in (v - radius, v + radius)
                    for b in (z - radius, z + radius)
                ]
                bounds.append(
                    (min(edges) - c.reprojection_error_px, max(edges) + c.reprojection_error_px)
                )
            left, right = bounds[0]
            top, bottom = bounds[1]
            finite((left, right, top, bottom))
            if not (
                0 <= left <= right <= c.camera.width - 1
                and 0 <= top <= bottom <= c.camera.height - 1
            ):
                raise ValueError("uncertainty_outside_image")
            result = RegisteredPoint(
                (x, y, z),
                pixel,
                (pixel[0] / c.camera.width, pixel[1] / c.camera.height),
                (left, top, right, bottom),
                radius,
                c.camera.range_m((x, y, z)),
                c.target_frame,
                self._calibration_digest,
                min(self.valid_until, capture_ns + AGE_NS - uncertainty_ns),
                self.pending_break,
            )
            self.pending_break = False
            return result
        except (ValueError, TypeError, OverflowError):
            self.pending_break = True
            return SourceFault("registration_unavailable")
