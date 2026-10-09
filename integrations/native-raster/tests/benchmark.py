"""Reproducible local comparison; reports measurements, never hardware qualification."""

import argparse
import hashlib
import json
import platform
import statistics
import time
import tracemalloc

from aethron_edge.sensors.geometry import Pinhole
from aethron_edge.sensors.packets import decode_image
from aethron_edge.sensors.raster_rectification import rectify_mono16_recorded
from aethron_edge.sensors.rectification import LensCalibration
from aethron_raster_native import rectify_recorded

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--memory", action="store_true", help="also run slower Python allocation tracing"
)
args = parser.parse_args()

camera = Pinhole(width=640, height=512, fx=300.0, fy=300.0, cx=320.0, cy=256.0)
lens = LensCalibration(
    camera=camera,
    output_camera=camera,
    distortion=(0.03, 0.001, 0.0001, -0.0001, 0.0),
    valid_radius=2.0,
)
frame = decode_image(
    {
        "modality": "lwir",
        "encoding": "mono16",
        "width": 640,
        "height": 512,
        "step": 1283,
        "is_bigendian": True,
    },
    bytes(range(256)) * (1283 * 512 // 256),
)
results = {}
reference = rectify_mono16_recorded(frame, lens)
for name, call in (("python", rectify_mono16_recorded), ("cpp20", rectify_recorded)):
    assert call(frame, lens) == reference
    wall, cpu = [], []
    for _ in range(5):
        begin, processor = time.perf_counter_ns(), time.process_time_ns()
        result = call(frame, lens)
        cpu.append((time.process_time_ns() - processor) / 1e6)
        wall.append((time.perf_counter_ns() - begin) / 1e6)
        assert result == reference
    peak = None
    if args.memory:
        tracemalloc.start()
        result = call(frame, lens)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    results[name] = {
        "median_wall_ms": statistics.median(wall),
        "median_cpu_ms": statistics.median(cpu),
        "wall_ms": wall,
        "python_traced_peak_bytes": peak,
    }
print(
    json.dumps(
        {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "pixels": 640 * 512,
            "repeats": 5,
            "parity": True,
            "output_sha256": hashlib.sha256(reference.data + reference.validity).hexdigest(),
            "results": results,
            "qualified": False,
        },
        indent=2,
    )
)
