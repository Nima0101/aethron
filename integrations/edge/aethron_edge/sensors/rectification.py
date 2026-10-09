"""Bounded sparse Brown-Conrady and angular fisheye rays using optional OpenCV.

No pixel resampling, guessed depth, stereo baseline or live qualification.
The invertibility checks are conservative over each model's declared domain;
calibrations outside this subset require a separately validated lens model.
"""

import math
from typing import Literal

from pydantic import Field, model_validator

from .geometry import Pinhole, finite
from .packets import Closed


class LensCalibration(Closed):
    camera: Pinhole
    output_camera: Pinhole
    distortion: tuple[float, float, float, float, float]
    valid_radius: float = Field(gt=0, le=3)

    @model_validator(mode="after")
    def well_conditioned(self):
        finite(self.distortion)
        if any(abs(v) > 2 for v in self.distortion):
            raise ValueError("distortion_outside_contract")
        for camera in (self.camera, self.output_camera):
            if not (
                camera.fx >= 1e-6
                and camera.fy >= 1e-6
                and -2 * camera.width <= camera.cx <= 3 * camera.width
                and -2 * camera.height <= camera.cy <= 3 * camera.height
            ):
                raise ValueError("intrinsics_outside_contract")
        k1, k2, p1, p2, k3 = self.distortion
        # Radial Jacobian eigenvalues are scale and scale+2*r^2*dscale/d(r^2).
        # Drop positive terms, bound each negative term on [0, valid_radius].
        scale = 1 + sum(
            min(k, 0) * self.valid_radius ** (2 * i) for i, k in enumerate((k1, k2, k3), 1)
        )
        radial = 1 + sum(
            min((2 * i + 1) * k, 0) * self.valid_radius ** (2 * i)
            for i, k in enumerate((k1, k2, k3), 1)
        )
        tangential = 8 * self.valid_radius * (abs(p1) + abs(p2))
        if min(scale, radial) - tangential <= 1e-6:
            raise ValueError("lens_may_fold")
        return self

    def rectify_points(self, points):
        try:
            if not isinstance(points, (tuple, list)) or len(points) > 4096:
                raise ValueError("point_limit")
            for point in points:
                if not isinstance(point, (tuple, list)) or len(point) != 2:
                    raise ValueError("invalid_point")
                finite(point)
                if not (
                    0 <= point[0] <= self.camera.width - 1
                    and 0 <= point[1] <= self.camera.height - 1
                ):
                    raise ValueError("outside_image")
            if not points:
                return []
        except (ValueError, TypeError, OverflowError):
            raise ValueError("invalid_rectification") from None
        try:
            import cv2
            import numpy as np
        except ImportError:
            raise RuntimeError("rectifier_unavailable") from None
        try:
            c = self.camera
            matrix = np.array([[c.fx, 0, c.cx], [0, c.fy, c.cy], [0, 0, 1]], dtype=np.float64)
            samples = np.array(points, dtype=np.float64).reshape(-1, 1, 2)
            coefficients = np.array(self.distortion, dtype=np.float64)
            rays = cv2.undistortPointsIter(
                samples,
                matrix,
                coefficients,
                None,
                None,
                (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 50, 1e-10),
            )
            result = []
            k1, k2, p1, p2, k3 = self.distortion
            for original, ray in zip(points, rays.reshape(-1, 2), strict=True):
                x, y = map(float, ray)
                finite((x, y))
                r2 = x * x + y * y
                if r2 > self.valid_radius**2:
                    raise ValueError("outside_calibrated_disk")
                scale = 1 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2
                xd = x * scale + 2 * p1 * x * y + p2 * (r2 + 2 * x * x)
                yd = y * scale + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
                if (
                    math.hypot(c.fx * xd + c.cx - original[0], c.fy * yd + c.cy - original[1])
                    > 1e-6
                ):
                    raise ValueError("inverse_not_converged")
                out = self.output_camera.project((x, y, 1.0))
                result.append(out)
            return result
        except (ValueError, TypeError, OverflowError, cv2.error):
            raise ValueError("invalid_rectification") from None

    def deproject(self, u, v, axial_depth_m):
        try:
            finite((axial_depth_m,))
            if not 0 < axial_depth_m <= 500:
                raise ValueError("invalid_depth")
            x, y = self.rectify_points([(u, v)])[0]
            return self.output_camera.deproject(x, y, axial_depth_m)
        except (ValueError, TypeError, OverflowError):
            raise ValueError("invalid_rectification") from None


class FisheyeCalibration(Closed):
    """Explicit OpenCV angular model, zero skew, bounded front-facing rays only."""

    model: Literal["opencv_fisheye_v1"]
    camera: Pinhole
    output_camera: Pinhole
    distortion: tuple[float, float, float, float]
    valid_theta_rad: float = Field(gt=0, le=math.atan(3))

    def _distorted_theta(self, theta):
        return theta * (1 + sum(k * theta ** (2 * i) for i, k in enumerate(self.distortion, 1)))

    @model_validator(mode="after")
    def well_conditioned(self):
        finite(self.distortion)
        if any(abs(v) > 2 for v in self.distortion):
            raise ValueError("distortion_outside_contract")
        for camera in (self.camera, self.output_camera):
            if not (
                camera.fx >= 1e-6
                and camera.fy >= 1e-6
                and -2 * camera.width <= camera.cx <= 3 * camera.width
                and -2 * camera.height <= camera.cy <= 3 * camera.height
            ):
                raise ValueError("intrinsics_outside_contract")
        # Conservative derivative lower bound on [0, valid_theta_rad]:
        # positive polynomial terms cannot reduce monotonicity. This also
        # guarantees positive angular scale since theta_d(0) = 0.
        slope = 1 + sum(
            min((2 * i + 1) * k, 0) * self.valid_theta_rad ** (2 * i)
            for i, k in enumerate(self.distortion, 1)
        )
        if slope <= 1e-6:
            raise ValueError("lens_may_fold")
        # OpenCV clips distorted angular radii at pi/2; do not admit that region.
        if self._distorted_theta(self.valid_theta_rad) >= math.pi / 2:
            raise ValueError("angular_domain_outside_solver")
        return self

    def rectify_points(self, points):
        try:
            if not isinstance(points, (tuple, list)) or len(points) > 4096:
                raise ValueError("point_limit")
            c = self.camera
            limit = self._distorted_theta(self.valid_theta_rad)
            for point in points:
                if not isinstance(point, (tuple, list)) or len(point) != 2:
                    raise ValueError("invalid_point")
                finite(point)
                if not (0 <= point[0] <= c.width - 1 and 0 <= point[1] <= c.height - 1):
                    raise ValueError("outside_image")
                if math.hypot((point[0] - c.cx) / c.fx, (point[1] - c.cy) / c.fy) > limit:
                    raise ValueError("outside_calibrated_disk")
            if not points:
                return []
        except (ValueError, TypeError, OverflowError):
            raise ValueError("invalid_rectification") from None
        try:
            import cv2
            import numpy as np
        except ImportError:
            raise RuntimeError("rectifier_unavailable") from None
        try:
            matrix = np.array([[c.fx, 0, c.cx], [0, c.fy, c.cy], [0, 0, 1]], dtype=np.float64)
            rays = cv2.fisheye.undistortPoints(
                np.array(points, dtype=np.float64).reshape(-1, 1, 2),
                matrix,
                np.array(self.distortion, dtype=np.float64),
                criteria=(cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 50, 1e-10),
            )
            result = []
            for original, ray in zip(points, rays.reshape(-1, 2), strict=True):
                x, y = map(float, ray)
                finite((x, y))
                r = math.hypot(x, y)
                theta = math.atan(r)
                if theta > self.valid_theta_rad:
                    raise ValueError("outside_calibrated_disk")
                scale = self._distorted_theta(theta) / r if r else 1.0
                if (
                    math.hypot(
                        c.fx * x * scale + c.cx - original[0], c.fy * y * scale + c.cy - original[1]
                    )
                    > 1e-6
                ):
                    raise ValueError("inverse_not_converged")
                result.append(self.output_camera.project((x, y, 1.0)))
            return result
        except (ValueError, TypeError, OverflowError, cv2.error):
            raise ValueError("invalid_rectification") from None

    def deproject(self, u, v, axial_depth_m):
        try:
            finite((axial_depth_m,))
            if not 0 < axial_depth_m <= 500:
                raise ValueError("invalid_depth")
            x, y = self.rectify_points([(u, v)])[0]
            return self.output_camera.deproject(x, y, axial_depth_m)
        except (ValueError, TypeError, OverflowError):
            raise ValueError("invalid_rectification") from None
