"""Thread-confined, bounded ROS sensor ingress; no commands or semantic inference.

Accept generated ROS messages or exact dictionaries for replay. ROS acquisition
stamps are not host monotonic time. An explicit mapping remains unqualified
until installation-specific clock evidence exists; raw frames never self-certify.
"""

import hashlib
import json
import math
import re
from dataclasses import dataclass, replace

from pydantic import Field

from ..sources.base import SourceFault
from .geometry import Pinhole
from .packets import Closed, Cloud, CloudLayout, Raster, decode_cloud, decode_image, layout_digest

AGE_NS = 100_000_000
MAX_NS = 2**63 - 1
FRAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:/[A-Za-z_][A-Za-z0-9_]*)*")


def _integer(value, low=0, high=MAX_NS):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("invalid_integer")
    return value


def _fields(value, names):
    expected = set(names.split())
    if type(value) is dict:
        result = value
    elif callable(getattr(value, "get_fields_and_field_types", None)):
        if set(value.get_fields_and_field_types()) != expected:
            raise ValueError("unexpected_fields")
        result = {name: getattr(value, name) for name in expected}
    else:
        raise ValueError("invalid_message")
    if set(result) != expected:
        raise ValueError("unexpected_fields")
    return result


def _frame(value):
    if type(value) is not str or len(value) > 128 or FRAME.fullmatch(value) is None:
        raise ValueError("invalid_frame")
    return value


def _header(value, *, zero=False):
    h = _fields(value, "stamp frame_id")
    stamp = _fields(h["stamp"], "sec nanosec")
    sec = _integer(stamp["sec"], high=2**31 - 1)
    nanos = _integer(stamp["nanosec"], high=999_999_999)
    return _integer(sec * 1_000_000_000 + nanos, low=0 if zero else 1), _frame(h["frame_id"])


def _bytes(value):
    # Native ROS uint8 arrays expose the buffer protocol. Check size before copy.
    try:
        view = memoryview(value)
        if (
            view.ndim != 1
            or view.itemsize != 1
            or not view.c_contiguous
            or view.nbytes > 8 * 1024 * 1024
        ):
            raise ValueError("invalid_payload")
        return view.tobytes()
    except TypeError as exc:
        raise ValueError("invalid_payload") from exc


def _vector(value, length):
    if not isinstance(value, (list, tuple)):
        try:
            view = memoryview(value)
            if view.ndim != 1 or len(view) != length or view.format not in {"f", "d"}:
                raise ValueError("invalid_vector")
            value = view.tolist()
        except TypeError as exc:
            raise ValueError("invalid_vector") from exc
    if len(value) != length:
        raise ValueError("invalid_vector")
    try:
        if not all(type(x) in (int, float) and math.isfinite(x) for x in value):
            raise ValueError("invalid_vector")
    except OverflowError as exc:
        raise ValueError("invalid_vector") from exc
    return list(value)


class ClockMapping(Closed):
    domain: str = Field(pattern=r"^ros_system$")
    offset_ns: int = Field(ge=-MAX_NS, le=MAX_NS)
    uncertainty_ns: int = Field(ge=0, le=50_000_000)
    valid_until_ns: int = Field(ge=0, le=MAX_NS)


@dataclass(frozen=True)
class RosObservation:
    payload: Raster | Cloud
    stamp_ns: int
    receive_ns: int
    frame_id: str
    capture_ns: int | None
    uncertainty_ns: int
    camera: Pinhole | None
    calibration_digest: str | None
    scene_break: bool
    layout_sha256: str | None = None

    @property
    def live_evidence(self):
        return False


class RosIngress:
    """One configured source, one pending raw frame; single executor ownership."""

    def __init__(self, *, modality, frame_id, meters_per_unit=None):
        if modality not in {"lwir", "nir", "depth", "radar", "lidar"}:
            raise ValueError("invalid_modality")
        if modality == "depth":
            if type(meters_per_unit) not in (int, float) or not 0 < meters_per_unit <= 1:
                raise ValueError("depth_scale_required")
        elif meters_per_unit is not None:
            raise ValueError("unexpected_depth_scale")
        self.modality = modality
        self.frame_id = _frame(frame_id)
        self.scale = meters_per_unit
        self.mapping = None
        self.calibration = None
        self.latest = None
        self.last_stamp = None
        self.last_layout = None
        self.last_receive = None
        self.pending_break = True
        self.received = 0
        self.overwritten = 0
        self.fault = None

    def bind_clock(self, mapping: ClockMapping):
        if not isinstance(mapping, ClockMapping):
            raise ValueError("invalid_clock_mapping")
        self.mapping = mapping
        self.latest = None
        self.pending_break = True

    def _fault(self, reason):
        self.latest = None
        self.pending_break = True
        self.fault = reason
        return SourceFault(reason)

    def camera_info(self, message, *, now_ns, valid_for_ns=30_000_000_000):
        _integer(now_ns)
        _integer(valid_for_ns, low=1, high=600_000_000_000)
        try:
            m = _fields(
                message, "header height width distortion_model d k r p binning_x binning_y roi"
            )
            _, frame = _header(m["header"], zero=True)
            if frame != self.frame_id or m["distortion_model"] not in {"", "plumb_bob"}:
                raise ValueError("unsupported_camera")
            if len(m["d"]) not in {0, 5} or any(_vector(m["d"], len(m["d"]))):
                raise ValueError("distortion_requires_rectification")
            k, rotation, p = _vector(m["k"], 9), _vector(m["r"], 9), _vector(m["p"], 12)
            if (
                rotation != [1, 0, 0, 0, 1, 0, 0, 0, 1]
                or k[1] != 0
                or k[3] != 0
                or k[6:] != [0, 0, 1]
            ):
                raise ValueError("unsupported_camera")
            if p != [k[0], 0, k[2], 0, 0, k[4], k[5], 0, 0, 0, 1, 0]:
                raise ValueError("unsupported_projection")
            for name in ("binning_x", "binning_y"):
                _integer(m[name], high=1)
            roi = _fields(m["roi"], "x_offset y_offset height width do_rectify")
            for name in ("x_offset", "y_offset", "height", "width"):
                _integer(roi[name], high=0)
            if roi["do_rectify"] is not False:
                raise ValueError("unsupported_roi")
            camera = Pinhole(
                width=m["width"], height=m["height"], fx=k[0], fy=k[4], cx=k[2], cy=k[5]
            )
            digest = hashlib.sha256(
                json.dumps({"frame": frame, **camera.model_dump()}, sort_keys=True).encode()
            ).hexdigest()
            if self.calibration is None or self.calibration[1] != digest:
                self.latest = None
                self.pending_break = True
            self.calibration = (camera, digest, min(MAX_NS, now_ns + valid_for_ns))
            return digest
        except (ValueError, TypeError, AttributeError, OverflowError):
            self.calibration = None
            return self._fault("calibration_invalid")

    def image(self, message, *, now_ns):
        _integer(now_ns)
        try:
            m = _fields(message, "header height width encoding is_bigendian step data")
            stamp, frame = _header(m["header"])
            if frame != self.frame_id:
                raise ValueError("frame_mismatch")
            big = bool(_integer(m["is_bigendian"], high=1))
            layout = {key: m[key] for key in ("height", "width", "encoding", "step")}
            layout.update(modality=self.modality, is_bigendian=big, meters_per_unit=self.scale)
            payload = decode_image(layout, _bytes(m["data"]))
            return self._accept(payload, stamp, now_ns)
        except (ValueError, TypeError, AttributeError, OverflowError):
            self.mapping = None
            self.last_stamp = None
            return self._fault("sensor_invalid")

    def pointcloud(self, message, *, now_ns):
        _integer(now_ns)
        try:
            m = _fields(
                message, "header height width fields is_bigendian point_step row_step data is_dense"
            )
            stamp, frame = _header(m["header"])
            if (
                frame != self.frame_id
                or self.modality not in {"radar", "lidar"}
                or type(m["is_dense"]) is not bool
            ):
                raise ValueError("invalid_cloud")
            if not isinstance(m["fields"], (list, tuple)) or not 3 <= len(m["fields"]) <= 4:
                raise ValueError("invalid_fields")
            layout = {
                key: m[key] for key in ("height", "width", "is_bigendian", "point_step", "row_step")
            }
            layout["fields"] = [_fields(f, "name offset datatype count") for f in m["fields"]]
            return self._accept(
                decode_cloud(layout, _bytes(m["data"])),
                stamp,
                now_ns,
                layout_digest(CloudLayout.model_validate(layout)),
            )
        except (ValueError, TypeError, AttributeError, OverflowError):
            self.mapping = None
            self.last_stamp = None
            return self._fault("sensor_invalid")

    def _accept(self, payload, stamp, now, format_digest=None):
        if self.last_stamp is not None and (stamp <= self.last_stamp or now < self.last_receive):
            self.mapping = None
            self.last_stamp = None
            return self._fault("clock_discontinuity")
        if self.last_receive is not None and now - self.last_receive > AGE_NS:
            self.pending_break = True
        capture = None
        uncertainty = 0
        if self.mapping is not None:
            if now > self.mapping.valid_until_ns:
                self.mapping = None
                self.pending_break = True
            else:
                capture = stamp + self.mapping.offset_ns
                uncertainty = self.mapping.uncertainty_ns
                if (
                    not 0 <= capture <= MAX_NS
                    or capture + uncertainty > now
                    or now - capture + uncertainty > AGE_NS
                ):
                    self.mapping = None
                    self.last_stamp = None
                    return self._fault("clock_discontinuity")
        if isinstance(payload, Raster):
            format_digest = layout_digest(payload.layout)
        if self.last_layout is not None and format_digest != self.last_layout:
            self.calibration = None
            self.pending_break = True
        self.last_layout = format_digest
        camera = digest = None
        if isinstance(payload, Raster) and self.calibration is not None:
            candidate, identity, expiry = self.calibration
            if now <= expiry and (candidate.width, candidate.height) == (
                payload.layout.width,
                payload.layout.height,
            ):
                camera, digest = candidate, identity
            else:
                self.calibration = None
                self.pending_break = True
        observation = RosObservation(
            payload,
            stamp,
            now,
            self.frame_id,
            capture,
            uncertainty,
            camera,
            digest,
            self.pending_break,
            format_digest,
        )
        if self.latest is not None:
            self.overwritten += 1
        self.latest = observation
        self.pending_break = False
        self.last_stamp = stamp
        self.last_receive = now
        self.fault = None
        self.received += 1
        return observation

    def take(self, *, now_ns):
        _integer(now_ns)
        if self.latest is None:
            return SourceFault("source_waiting")
        age = now_ns - (
            self.latest.capture_ns if self.latest.capture_ns is not None else self.latest.receive_ns
        )
        if age < 0 or age + self.latest.uncertainty_ns > AGE_NS:
            return self._fault("source_timeout")
        result, self.latest = self.latest, None
        if result.capture_ns is not None and (
            self.mapping is None or now_ns > self.mapping.valid_until_ns
        ):
            self.mapping = None
            self.pending_break = True
            result = replace(result, capture_ns=None, uncertainty_ns=0, scene_break=True)
        if result.camera is not None and (self.calibration is None or now_ns > self.calibration[2]):
            self.calibration = None
            self.pending_break = True
            result = replace(result, camera=None, calibration_digest=None, scene_break=True)
        return result

    def status(self, *, now_ns):
        _integer(now_ns)
        current = self.last_receive is not None and 0 <= now_ns - self.last_receive <= AGE_NS
        return {
            "version": 1,
            "emitted_ns": now_ns,
            "expires_ns": min(MAX_NS, now_ns + AGE_NS),
            "clock_domain": "host_monotonic",
            "state": "UNKNOWN",
            "qualified": False,
            "source_state": "invalid" if self.fault else "receiving" if current else "lost",
            "received": self.received,
            "overwritten": self.overwritten,
        }
