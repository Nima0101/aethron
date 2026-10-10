"""Bounded technology audit; synthetic packets and complete Python result conversion."""

import json
import math
import os
import platform
import select
import statistics
import struct
import subprocess
import time
from itertools import chain
from pathlib import Path

import numpy as np
from aethron_edge.sensors.packets import Cloud, CloudLayout, Point, decode_cloud

# Assertions also consume the worker handshake and execute warm-up candidates.
# Reject optimized imports as well as CLI execution before exposing these helpers.
if not __debug__:
    raise SystemExit("packet_audit_requires_assertions")


def validated(layout, data):
    spec = CloudLayout.model_validate(layout)
    if type(data) is not bytes or len(data) != spec.row_step * spec.height:
        raise ValueError("invalid_cloud_bytes")
    return spec


def scalar_baseline(layout, data):
    """Retained pre-audit kernel, with the same strict validation and result ABI."""
    s = validated(layout, data)
    points, samples = [], []
    endian = ">" if s.is_bigendian else "<"
    for y in range(s.height):
        for x in range(s.width):
            start = y * s.row_step + x * s.point_step
            values = {
                f.name: struct.unpack_from(
                    endian + ("f" if f.datatype == 7 else "d"), data, start + f.offset
                )[0]
                for f in s.fields
            }
            if not all(math.isfinite(v) for v in values.values()):
                samples.append(None)
                continue
            point = Point((values["x"], values["y"], values["z"]), values.get("radial_velocity"))
            points.append(point)
            samples.append(point)
    return Cloud(tuple(points), len(samples) - len(points), tuple(samples))


def assemble(rows, order):
    ix, iy, iz = (order.index(n) for n in ("x", "y", "z"))
    radial = order.index("radial_velocity") if "radial_velocity" in order else None
    samples, points = [], []
    for row in rows:
        if not all(math.isfinite(v) for v in row):
            samples.append(None)
            continue
        point = Point((row[ix], row[iy], row[iz]), None if radial is None else row[radial])
        samples.append(point)
        points.append(point)
    return Cloud(tuple(points), len(samples) - len(points), tuple(samples))


def compiled(layout, data):
    s = validated(layout, data)
    fields = sorted(s.fields, key=lambda f: f.offset)
    fmt = ">" if s.is_bigendian else "<"
    end = 0
    for f in fields:
        fmt += "x" * (f.offset - end) + ("f" if f.datatype == 7 else "d")
        end = f.offset + (4 if f.datatype == 7 else 8)
    unpack = struct.Struct(fmt).unpack_from
    rows = (
        unpack(data, y * s.row_step + x * s.point_step)
        for y in range(s.height)
        for x in range(s.width)
    )
    return assemble(rows, [f.name for f in fields])


def numpy_view(layout, data):
    s = validated(layout, data)
    dtype = np.dtype(
        {
            "names": [f.name for f in s.fields],
            "formats": [
                (">" if s.is_bigendian else "<") + ("f4" if f.datatype == 7 else "f8")
                for f in s.fields
            ],
            "offsets": [f.offset for f in s.fields],
            "itemsize": s.point_step,
        }
    )
    rows = np.ndarray(
        (s.height, s.width), dtype=dtype, buffer=data, strides=(s.row_step, s.point_step)
    ).tolist()
    return assemble(chain.from_iterable(rows), [f.name for f in s.fields])


class Node:
    def __init__(self, layout):
        start = time.perf_counter_ns()
        self.worker = subprocess.Popen(
            [
                "node",
                "--v8-pool-size=1",
                str(Path(__file__).with_name("buffer_worker.cjs")),
                json.dumps(layout),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(os.environ, UV_THREADPOOL_SIZE="1"),
        )
        try:
            assert self.read(1) == b"\1"
            self.startup_ms = (time.perf_counter_ns() - start) / 1e6
            self.rss_kib = None
            status = Path(f"/proc/{self.worker.pid}/status")
            if status.exists():
                for line in status.read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        self.rss_kib = int(line.split()[1])
        except BaseException:
            self.close()
            raise

    def read(self, size):
        result = bytearray()
        while len(result) < size:
            if not select.select([self.worker.stdout], [], [], 10)[0]:
                raise TimeoutError("audit_worker_timeout")
            block = os.read(self.worker.stdout.fileno(), size - len(result))
            if not block:
                raise ValueError("audit_worker_closed")
            result.extend(block)
        return bytes(result)

    def decode(self, layout, data):
        s = validated(layout, data)
        self.worker.stdin.write(data)
        self.worker.stdin.flush()
        result = self.read(s.width * s.height * 33 + 8)
        duration = struct.unpack_from("<d", result)[0]
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("invalid_worker_cpu_duration")
        self.last_kernel_cpu_ms = duration
        samples, points = [], []
        radial = any(f.name == "radial_velocity" for f in s.fields)
        for valid, x, y, z, velocity in struct.iter_unpack("<Bdddd", memoryview(result)[8:]):
            point = Point((x, y, z), velocity if radial else None) if valid else None
            samples.append(point)
            if point is not None:
                points.append(point)
        return Cloud(tuple(points), len(samples) - len(points), tuple(samples))

    def close(self):
        try:
            try:
                self.worker.stdin.close()
            finally:
                try:
                    self.worker.wait(timeout=5)
                finally:
                    if self.worker.poll() is None:
                        self.worker.kill()
                        self.worker.wait(timeout=5)
        finally:
            try:
                self.worker.stdout.close()
            finally:
                self.worker.stderr.close()


def fixture(big, mixed):
    fields = [
        {"name": "z", "offset": 17 if mixed else 8, "datatype": 8 if mixed else 7, "count": 1},
        {"name": "x", "offset": 1 if mixed else 0, "datatype": 8 if mixed else 7, "count": 1},
        {"name": "radial_velocity", "offset": 25 if mixed else 12, "datatype": 7, "count": 1},
        {"name": "y", "offset": 9 if mixed else 4, "datatype": 8 if mixed else 7, "count": 1},
    ]
    s = {
        "width": 64,
        "height": 64,
        "point_step": 32,
        "row_step": 2061,
        "is_bigendian": big,
        "fields": fields,
    }
    raw = bytearray(s["row_step"] * s["height"])
    for y in range(s["height"]):
        for x in range(s["width"]):
            i = y * s["width"] + x
            for f in fields:
                value = {"x": i / 32, "y": -2.5, "z": 3.0, "radial_velocity": -0.5}[f["name"]]
                if i % 17 == 0 and f["name"] == "x":
                    value = float("nan")
                struct.pack_into(
                    (">" if big else "<") + ("f" if f["datatype"] == 7 else "d"),
                    raw,
                    y * s["row_step"] + x * s["point_step"] + f["offset"],
                    value,
                )
    return s, bytes(raw)


def measure_all(functions, layout, data, expected, node):
    samples = {
        name: {"wall": [], "parent_cpu": [], "cpu_with_worker_kernel": []} for name in functions
    }
    for fn in functions.values():
        assert fn(layout, data) == expected
    names = list(functions)
    for iteration in range(15):
        # Rotate order to avoid assigning every candidate a separate contention window.
        for name in names[iteration % len(names) :] + names[: iteration % len(names)]:
            start, cpu_start = time.perf_counter_ns(), time.process_time_ns()
            result = functions[name](layout, data)
            cpu = (time.process_time_ns() - cpu_start) / 1e6
            wall = (time.perf_counter_ns() - start) / 1e6
            assert result == expected
            samples[name]["wall"].append(wall)
            samples[name]["parent_cpu"].append(cpu)
            samples[name]["cpu_with_worker_kernel"].append(
                cpu + (node.last_kernel_cpu_ms if name == "node_buffer" else 0)
            )
    return {
        name: {
            "wall_p50_ms": statistics.median(s["wall"]),
            "wall_p95_ms": sorted(s["wall"])[14],
            "parent_cpu_p50_ms": statistics.median(s["parent_cpu"]),
            "cpu_with_worker_kernel_p50_ms": statistics.median(s["cpu_with_worker_kernel"]),
        }
        for name, s in samples.items()
    }


def main():
    report = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        "method": "15 rotated paired samples; worker kernel CPU added to parent CPU, worker pipe I/O CPU excluded",
        "cases": [],
    }
    for big, mixed in ((False, False), (True, True)):
        layout, data = fixture(big, mixed)
        expected = scalar_baseline(layout, data)
        assert len(expected.sample_points) == 4096 and expected.invalid_points == 241
        case = {"bigendian": big, "mixed_unaligned": mixed, "bytes": len(data), "parity": True}
        node = Node(layout)
        try:
            case.update(
                measure_all(
                    {
                        "baseline": scalar_baseline,
                        "production": decode_cloud,
                        "compiled_struct": compiled,
                        "numpy_view": numpy_view,
                        "node_buffer": node.decode,
                    },
                    layout,
                    data,
                    expected,
                    node,
                )
            )
            case["node_buffer"].update(startup_ms=node.startup_ms, worker_rss_kib=node.rss_kib)
        finally:
            node.close()
        report["cases"].append(case)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
