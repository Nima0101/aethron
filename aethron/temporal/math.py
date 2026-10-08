"""Independent bounded geometry, optimal assignment and constant-velocity filtering."""

from statistics import median

from ..schema import require
from .schema import number


def centre(b):
    return b[0] + b[2] / 2, b[1] + b[3] / 2


def iou(a, b):
    area = max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])) * max(
        0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    )
    union = a[2] * a[3] + b[2] * b[3] - area
    return min(1.0, max(0.0, area / union)) if union > 0 else 0.0


def assignment(cost):
    """Rectangular Hungarian potentials; rows<=columns, deterministic ties. No dependencies."""
    n = len(cost)
    if not n:
        return []
    m = len(cost[0])
    require(n <= m <= 128 and n <= 64)
    for row in cost:
        require(len(row) == m)
        for val in row:
            number(val, 0, 1000000)
    u, v, p, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        mins, used = [float("inf")] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], float("inf"), 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < mins[j]:
                        mins[j], way[j] = cur, j0
                    if mins[j] < delta:
                        delta, j1 = mins[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    mins[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    return sorted((p[j] - 1, j - 1) for j in range(1, m + 1) if p[j])


class Axis:
    """Two-state Kalman filter. Joseph covariance update avoids cancellation."""

    def __init__(self, position, variance):
        self.x, self.v = position, 0.0
        self.a, self.b, self.c = variance, 0.0, 0.25

    def predict(self, dt, shift, variance):
        self.x += self.v * dt + shift
        self.a += 2 * dt * self.b + dt * dt * self.c + 0.01 * dt**4 / 4 + variance
        self.b += dt * self.c + 0.01 * dt**3 / 2
        self.c += 0.01 * dt * dt

    def update(self, z, noise):
        denom = self.a + noise
        k, gain_velocity = self.a / denom, self.b / denom
        err = z - self.x
        self.x += k * err
        self.v += gain_velocity * err
        a, b, c = self.a, self.b, self.c
        self.a = (1 - k) ** 2 * a + k * k * noise
        self.b = (1 - k) * (b - gain_velocity * a) + k * gain_velocity * noise
        self.c = (
            c
            - 2 * gain_velocity * b
            + gain_velocity * gain_velocity * a
            + gain_velocity * gain_velocity * noise
        )


def translation(samples, *, spatially_distributed):
    """Adapter supplies non-person background displacement samples, never appearance."""
    require(type(samples) is list and len(samples) <= 256)
    require(type(spatially_distributed) is bool)
    for item in samples:
        require(type(item) is list and len(item) == 2)
        for val in item:
            number(val, -0.25, 0.25)
    invalid = {"dx": 0.0, "dy": 0.0, "variance": 0.05, "valid": False}
    if len(samples) < 6 or not spatially_distributed:
        return invalid
    dx, dy = median(s[0] for s in samples), median(s[1] for s in samples)
    inliers = [s for s in samples if (s[0] - dx) ** 2 + (s[1] - dy) ** 2 <= 0.01**2]
    if len(inliers) / len(samples) < 0.6:
        return invalid
    variance = max(
        sum((s[0] - dx) ** 2 + (s[1] - dy) ** 2 for s in inliers) / len(inliers), 0.000001
    )
    return {"dx": dx, "dy": dy, "variance": variance, "valid": True}
