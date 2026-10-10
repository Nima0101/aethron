"""Synthetic C03 scalar-boundary comparison; no hardware accuracy claim."""

import hashlib
import json
import math
import statistics
import time
import tracemalloc
from pathlib import Path

import numpy as np
from aethron_edge.sensors import geometry
from aethron_edge.sensors.geometry import Pinhole, finite

# Admission and warm-up parity assertions must run before reporting evidence.
if not __debug__:
    raise SystemExit("geometry_audit_requires_assertions")


class NumpyPinhole(Pinhole):
    def project(self, xyz_m):
        if not isinstance(xyz_m, (tuple, list)) or len(xyz_m) != 3:
            raise ValueError("invalid_point")
        finite(xyz_m)
        if xyz_m[2] <= 0:
            raise ValueError("behind_camera")
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            uv = np.array((self.fx, self.fy)) * np.array(xyz_m[:2]) / xyz_m[2]
            uv += (self.cx, self.cy)
        result = tuple(map(float, uv))
        finite(result)
        if not (0 <= result[0] <= self.width - 1 and 0 <= result[1] <= self.height - 1):
            raise ValueError("outside_image")
        return result

    def deproject(self, u, v, depth_m):
        finite((u, v, depth_m))
        if not (0 <= u <= self.width - 1 and 0 <= v <= self.height - 1 and 0 < depth_m <= 500):
            raise ValueError("outside_projection_domain")
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            xy = (np.array((u, v)) - (self.cx, self.cy)) / (self.fx, self.fy) * depth_m
        result = (float(xy[0]), float(xy[1]), depth_m)
        finite(result)
        return result

    @staticmethod
    def range_m(xyz_m):
        if not isinstance(xyz_m, (tuple, list)) or len(xyz_m) != 3:
            raise ValueError("invalid_point")
        finite(xyz_m)
        # Squared-sum norm underflows for valid tiny vectors; use stable hypot.
        result = float(np.hypot.reduce(xyz_m))
        if not 0 < result <= 500:
            raise ValueError("outside_range_contract")
        return result


def outcome(camera, operation, args):
    try:
        return ("accepted", getattr(camera, operation)(*args))
    except ValueError as exc:
        return ("rejected", str(exc))


def main():
    if tracemalloc.is_tracing():
        raise ValueError("geometry_audit_tracing_active")
    source_paths = {
        "compare.py": Path(__file__),
        "aethron_edge.sensors.geometry": Path(geometry.__file__),
    }
    source_sha256 = {
        name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in source_paths.items()
    }
    spec = {"width": 640, "height": 480, "fx": 400.0, "fy": 400.0, "cx": 320.0, "cy": 240.0}
    cameras = {"production": Pinhole(**spec), "numpy": NumpyPinhole(**spec)}
    cases = [
        ("project", ((x, y, z),))
        for x, y, z in (
            (0, 0, 1),
            (-0.8, -0.6, 1),
            (0.7975, 0.5975, 1),
            (0, 0, 0),
            (0, 0, -1),
            (True, 0, 1),
            (float("nan"), 0, 1),
            (1e308, 0, 1),
            (0, 0, 10**400),
            (0, 0, 5e-324),
        )
    ]
    cases += [
        ("range_m", (p,))
        for p in (
            (1e-300, 0, 0),
            (3, 4, 0),
            (500, 0, 0),
            (math.nextafter(500, math.inf), 0, 0),
            (0, 0, 0),
            (False, 0, 1),
        )
    ]
    cases += [
        ("deproject", args)
        for args in (
            (0, 0, 1),
            (639, 479, 500),
            (640, 1, 1),
            (1, 1, 0),
            (False, 1, 1),
            (1, 1, float("inf")),
        )
    ]
    for operation, args in cases:
        expected = outcome(cameras["production"], operation, args)
        actual = outcome(cameras["numpy"], operation, args)
        assert actual == expected, (operation, args, actual, expected)
    report = {
        "source_sha256": source_sha256,
        "numpy": np.__version__,
        "contract_cases": len(cases),
        "parity": True,
        "naive_norm_counterexample": {
            "input": [1e-300, 0, 0],
            "hypot": math.hypot(1e-300, 0, 0),
            "numpy_norm": float(np.linalg.norm([1e-300, 0, 0])),
        },
        "batches": {},
    }
    for count in (1, 64):
        points = [(i / 200, -i / 300, 2 + i / 10) for i in range(count)]

        def run(camera, points=points):
            output = []
            for p in points:
                uv = camera.project(p)
                output.append((uv, camera.deproject(*uv, p[2]), camera.range_m(p)))
            return output

        expected = run(cameras["production"])
        actual = run(cameras["numpy"])
        for a, b in zip(actual, expected, strict=True):
            assert np.allclose((*a[0], *a[1], a[2]), (*b[0], *b[1], b[2]), rtol=1e-14, atol=0)
        samples = {key: {"cpu": [], "wall": []} for key in cameras}
        names = list(cameras)
        for i in range(15):
            for key in names[i % 2 :] + names[: i % 2]:
                start, cpu = time.perf_counter_ns(), time.process_time_ns()
                for _ in range(20):
                    run(cameras[key])
                samples[key]["cpu"].append((time.process_time_ns() - cpu) / 20e6)
                samples[key]["wall"].append((time.perf_counter_ns() - start) / 20e6)
        result = {}
        for key in cameras:
            tracemalloc.start()
            try:
                output = run(cameras[key])
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
            del output
            result[key] = {
                "cpu_p50_ms": statistics.median(samples[key]["cpu"]),
                "wall_p50_ms": statistics.median(samples[key]["wall"]),
                "traced_peak_bytes": peak,
            }
        report["batches"][str(count)] = result
    for name, path in source_paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != source_sha256[name]:
            raise RuntimeError("geometry_audit_source_changed")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
