"""Raw Image/PointCloud2 data decoding, separate from semantic perception.

Layouts follow the pinned official sources in P2-SENSOR-ADAPTERS.md. Callers
supply acquisition clocks and calibration separately. No IDs, inferred image
boxes, temperature conversion or device activation are introduced here.
"""

import hashlib
import json
import math
import struct
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_BYTES = 8 * 1024 * 1024
MAX_POINTS = 4096


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class ImageLayout(Closed):
    modality: Literal["lwir", "nir", "depth"]
    encoding: Literal["mono8", "mono16", "16UC1", "32FC1"]
    width: int = Field(ge=1, le=1920)
    height: int = Field(ge=1, le=1080)
    step: int = Field(ge=1, le=8192)
    is_bigendian: bool
    meters_per_unit: float | None = Field(default=None, gt=0, le=1)

    @model_validator(mode="after")
    def layout(self):
        if self.modality == "depth":
            if self.encoding not in {"16UC1", "32FC1"} or self.meters_per_unit is None:
                raise ValueError("depth_scale_required")
            if self.encoding == "32FC1" and self.meters_per_unit != 1:
                raise ValueError("float_depth_meters_required")
        elif self.encoding not in {"mono8", "mono16"} or self.meters_per_unit is not None:
            raise ValueError("intensity_is_not_distance")
        if self.step < self.width * self.bytes_per_pixel or self.step * self.height > MAX_BYTES:
            raise ValueError("image_size_limit")
        return self

    @property
    def bytes_per_pixel(self):
        return {"mono8": 1, "mono16": 2, "16UC1": 2, "32FC1": 4}[self.encoding]


@dataclass(frozen=True)
class Raster:
    layout: ImageLayout
    data: bytes = field(repr=False)

    @property
    def units(self):
        return "meters_after_scale" if self.layout.modality == "depth" else "counts"

    def sample(self, x: int, y: int):
        spec = self.layout
        if (
            type(x) is not int
            or type(y) is not int
            or not (0 <= x < spec.width and 0 <= y < spec.height)
        ):
            raise ValueError("pixel_outside_frame")
        fmt = {"mono8": "B", "mono16": "H", "16UC1": "H", "32FC1": "f"}[spec.encoding]
        return struct.unpack_from(
            (">" if spec.is_bigendian else "<") + fmt,
            self.data,
            y * spec.step + x * spec.bytes_per_pixel,
        )[0]

    def depth_m(self, x: int, y: int):
        if self.layout.modality != "depth":
            raise ValueError("not_a_depth_frame")
        value = self.sample(x, y) * self.layout.meters_per_unit
        # Missing/out-of-contract range is unknown, never free space.
        return value if math.isfinite(value) and 0 < value <= 500 else None


def decode_image(layout: dict, data: bytes) -> Raster:
    spec = ImageLayout.model_validate(layout)
    if type(data) is not bytes or len(data) != spec.step * spec.height:
        raise ValueError("invalid_image_bytes")
    return Raster(spec, data)


class PointField(Closed):
    name: Literal["x", "y", "z", "radial_velocity"]
    offset: int = Field(ge=0, le=120)
    datatype: Literal[7, 8]
    count: Literal[1]

    @model_validator(mode="before")
    @classmethod
    def numeric_literals(cls, value):
        if isinstance(value, dict) and any(
            type(value.get(k)) is not int for k in ("datatype", "count")
        ):
            raise ValueError("invalid_field_type")
        return value


class CloudLayout(Closed):
    width: int = Field(ge=0, le=MAX_POINTS)
    height: int = Field(ge=1, le=MAX_POINTS)
    point_step: int = Field(ge=12, le=128)
    row_step: int = Field(ge=0, le=MAX_BYTES)
    is_bigendian: bool
    fields: list[PointField] = Field(min_length=3, max_length=4)

    @model_validator(mode="after")
    def layout(self):
        names = [f.name for f in self.fields]
        if not {"x", "y", "z"} <= set(names) or len(set(names)) != len(names):
            raise ValueError("invalid_point_fields")
        if (
            self.width * self.height > MAX_POINTS
            or self.row_step < self.width * self.point_step
            or self.row_step * self.height > MAX_BYTES
        ):
            raise ValueError("cloud_size_limit")
        used = set()
        for entry in self.fields:
            size = 4 if entry.datatype == 7 else 8
            span = set(range(entry.offset, entry.offset + size))
            if entry.offset + size > self.point_step or span & used:
                raise ValueError("overlapping_point_fields")
            used.update(span)
        return self


@dataclass(frozen=True)
class Point:
    xyz_m: tuple[float, float, float]
    radial_velocity_mps: float | None = None


@dataclass(frozen=True)
class Cloud:
    points: tuple[Point, ...]
    invalid_points: int
    # Packet ordinal positions, including invalid samples; points remains the finite view.
    sample_points: tuple[Point | None, ...]


def decode_cloud(layout: dict, data: bytes) -> Cloud:
    spec = CloudLayout.model_validate(layout)
    if type(data) is not bytes or len(data) != spec.row_step * spec.height:
        raise ValueError("invalid_cloud_bytes")
    points = []
    samples = []
    invalid = 0
    endian = ">" if spec.is_bigendian else "<"
    for y in range(spec.height):
        for x in range(spec.width):
            start = y * spec.row_step + x * spec.point_step
            values = {
                f.name: struct.unpack_from(
                    endian + ("f" if f.datatype == 7 else "d"), data, start + f.offset
                )[0]
                for f in spec.fields
            }
            if not all(math.isfinite(v) for v in values.values()):
                invalid += 1
                samples.append(None)
                continue
            point = Point((values["x"], values["y"], values["z"]), values.get("radial_velocity"))
            points.append(point)
            samples.append(point)
    return Cloud(tuple(points), invalid, tuple(samples))


def layout_digest(layout):
    """Pin physical sample format; cloud counts/padding are packet metadata."""
    if not isinstance(layout, (ImageLayout, CloudLayout)):
        raise ValueError("invalid_layout")
    fields = layout.model_dump()
    if isinstance(layout, CloudLayout):
        for name in ("width", "height", "row_step"):
            fields.pop(name)
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
