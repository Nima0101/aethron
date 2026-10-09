"""Recorded intensity count remapping v1; no live admission or calibration claim."""

import math
from dataclasses import dataclass, field
from typing import Literal

from .packets import Raster, decode_image
from .rectification import FisheyeCalibration, LensCalibration

MAX_OUTPUT_PIXELS = 640 * 512


@dataclass(frozen=True)
class _RectifiedCounts:
    width: int
    height: int
    modality: str
    data: bytes = field(repr=False)
    validity: bytes = field(repr=False)

    @property
    def version(self) -> Literal[1]:
        return 1

    @property
    def live_evidence(self) -> Literal[False]:
        return False

    def _index(self, x, y):
        if (
            type(x) is not int
            or type(y) is not int
            or not (0 <= x < self.width and 0 <= y < self.height)
        ):
            raise ValueError("pixel_outside_frame")
        return y * self.width + x


@dataclass(frozen=True)
class RectifiedMono8(_RectifiedCounts):
    def sample(self, x, y):
        index = self._index(x, y)
        return self.data[index] if self.validity[index] else None


@dataclass(frozen=True)
class RectifiedMono16(_RectifiedCounts):
    @property
    def encoding(self) -> Literal["mono16"]:
        return "mono16"

    @property
    def is_bigendian(self) -> Literal[False]:
        return False

    def sample(self, x, y):
        index = self._index(x, y)
        if not self.validity[index]:
            return None
        return int.from_bytes(self.data[2 * index : 2 * index + 2], "little")


def rectify_mono8_recorded(frame, lens):
    """Return packed nearest-neighbour counts and a 0/1 validity byte per output pixel.

    Output centres map forward through the declared lens into the raw image.
    Invalid rays retain zero storage but sample as None, never as zero evidence.
    The caller must preserve the mask; this result cannot authorize live support.
    """
    return _rectify_recorded(frame, lens, "mono8", 1, RectifiedMono8)


def rectify_mono16_recorded(frame, lens):
    """Remap unsigned counts to packed little-endian mono16 with a separate 0/1 mask."""
    return _rectify_recorded(frame, lens, "mono16", 2, RectifiedMono16)


def _rectify_recorded(frame, lens, encoding, bytes_per_pixel, result_type):
    try:
        if type(frame) is not Raster or type(lens) not in (LensCalibration, FisheyeCalibration):
            raise ValueError("unsupported_input")
        # Revalidate even model_construct/model_copy objects; neither is a trust boundary.
        lens = type(lens).model_validate(lens.model_dump())
        frame = decode_image(frame.layout.model_dump(), frame.data)
        c, out = lens.camera, lens.output_camera
        if (
            frame.layout.encoding != encoding
            or (frame.layout.width, frame.layout.height) != (c.width, c.height)
            or out.width * out.height > MAX_OUTPUT_PIXELS
        ):
            raise ValueError("raster_contract")
        validity = bytearray(out.width * out.height)
        data = bytearray(len(validity) * bytes_per_pixel)
        brown = type(lens) is LensCalibration
        identity = brown and c == out and not any(lens.distortion)
        for row in range(out.height):
            y = (row - out.cy) / out.fy
            for col in range(out.width):
                x = (col - out.cx) / out.fx
                if brown:
                    r2 = x * x + y * y
                    if r2 > lens.valid_radius**2:
                        continue
                    k1, k2, p1, p2, k3 = lens.distortion
                    scale = 1 + k1 * r2 + k2 * r2**2 + k3 * r2**3
                    xd = x * scale + 2 * p1 * x * y + p2 * (r2 + 2 * x * x)
                    yd = y * scale + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
                else:
                    radius = math.hypot(x, y)
                    theta = math.atan(radius)
                    if theta > lens.valid_theta_rad:
                        continue
                    scale = lens._distorted_theta(theta) / radius if radius else 1.0
                    xd, yd = x * scale, y * scale
                u, v = (col, row) if identity else (c.fx * xd + c.cx, c.fy * yd + c.cy)
                # Check continuous coordinates first: never round/clamp an outside ray inward.
                if not (0 <= u <= c.width - 1 and 0 <= v <= c.height - 1):
                    continue
                sx, sy = math.floor(u + 0.5), math.floor(v + 0.5)
                index = row * out.width + col
                offset = sy * frame.layout.step + sx * bytes_per_pixel
                pixel = frame.data[offset : offset + bytes_per_pixel]
                if frame.layout.is_bigendian:
                    pixel = pixel[::-1]
                start = index * bytes_per_pixel
                data[start : start + bytes_per_pixel] = pixel
                validity[index] = 1
        return result_type(
            out.width, out.height, frame.layout.modality, bytes(data), bytes(validity)
        )
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ValueError("invalid_raster_rectification") from None
