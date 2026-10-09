"""Rectified optical-frame geometry only; never a physical calibration claim."""

import math

from pydantic import Field

from .packets import Closed


def finite(values):
    try:
        valid = all(type(v) in (int, float) and math.isfinite(v) for v in values)
    except (OverflowError, TypeError):
        valid = False
    if not valid:
        raise ValueError("invalid_geometry")


class Pinhole(Closed):
    width: int = Field(ge=1, le=1920)
    height: int = Field(ge=1, le=1080)
    fx: float = Field(gt=0, le=100000)
    fy: float = Field(gt=0, le=100000)
    cx: float
    cy: float

    def deproject(self, u: float, v: float, depth_m: float):
        finite((u, v, depth_m))
        if not (0 <= u <= self.width - 1 and 0 <= v <= self.height - 1 and 0 < depth_m <= 500):
            raise ValueError("outside_projection_domain")
        result = ((u - self.cx) / self.fx * depth_m, (v - self.cy) / self.fy * depth_m, depth_m)
        finite(result)
        return result

    def project(self, xyz_m):
        if not isinstance(xyz_m, (tuple, list)) or len(xyz_m) != 3:
            raise ValueError("invalid_point")
        finite(xyz_m)
        x, y, z = xyz_m
        if z <= 0:
            raise ValueError("behind_camera")
        u, v = self.fx * x / z + self.cx, self.fy * y / z + self.cy
        finite((u, v))
        if not (0 <= u <= self.width - 1 and 0 <= v <= self.height - 1):
            raise ValueError("outside_image")
        return u, v

    @staticmethod
    def range_m(xyz_m):
        if not isinstance(xyz_m, (tuple, list)) or len(xyz_m) != 3:
            raise ValueError("invalid_point")
        finite(xyz_m)
        result = math.hypot(*xyz_m)
        if not 0 < result <= 500:
            raise ValueError("outside_range_contract")
        return result
