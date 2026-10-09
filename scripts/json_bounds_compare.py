"""Bounded P1.1 guard comparison; timings are evidence, never qualification."""

import argparse
import hashlib
import importlib.machinery
import io
import json
import platform
import re
import runpy
import statistics
import time
import tracemalloc
from pathlib import Path

from aethron import _json_bounds, schema
from aethron.temporal.replay import replay

TOKENS = re.compile(rb'["\\\[\]{}]')


def regex_check(data):
    if type(data) is not bytes or len(data) > 65536:
        return False
    depth, escaped_at = 0, -1
    quoted = False
    for match in TOKENS.finditer(data):
        at = match.start()
        char = data[at]
        if quoted:
            if at == escaped_at:
                continue
            if char == 92:
                escaped_at = at + 1
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):
            depth += 1
            if depth > 8:
                return False
        elif char in (93, 125):
            depth -= 1
            if depth < 0:
                return False
    return True


def measure(function, data, iterations):
    cpu, wall = [], []
    for _ in range(3):
        start, cpu_start = time.perf_counter_ns(), time.process_time_ns()
        for _ in range(iterations):
            function(data)
        cpu.append((time.process_time_ns() - cpu_start) / iterations / 1000)
        wall.append((time.perf_counter_ns() - start) / iterations / 1000)
    tracemalloc.start()
    try:
        function(data)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    return {
        "cpu_median_us": statistics.median(cpu),
        "wall_median_us": statistics.median(wall),
        "python_traced_peak_bytes": peak,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args()
    compiled = any(
        _json_bounds.__file__.endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES
    )
    if args.require_native and not compiled:
        raise RuntimeError("native_backend_missing")
    source = Path(_json_bounds.__file__).with_name("_json_bounds.py")
    pure = runpy.run_path(str(source))["check"]
    root = Path(__file__).resolve().parents[1]
    recording = (root / "examples/temporal-blackout.jsonl").read_bytes()
    normal = recording.splitlines()[0]
    workloads = {
        "normal_v3": normal,
        "padded_v3": normal + b" " * (65536 - len(normal)),
        "dense_structural": b"[]" * 32768,
        "escaped_string": b'"' + b"\\" * 65534 + b'"',
    }
    results = {}
    original = schema.check_bounds
    try:
        for name, function in (
            ("python_loop", pure),
            ("regex_tokens", regex_check),
            ("installed", _json_bounds.check),
        ):
            for data in workloads.values():
                if function(data) != pure(data):
                    raise RuntimeError("guard_parity_failed")
            guard = {label: measure(function, data, 20) for label, data in workloads.items()}
            schema.check_bounds = function
            parsing = {}
            for label in ("normal_v3", "padded_v3"):
                data = workloads[label]
                if schema.parse(data) != json.loads(normal):
                    raise RuntimeError("parser_parity_failed")
                parsing[label] = measure(schema.parse, data, 20)

            def replay_recording(data):
                return list(replay(io.BytesIO(data)))

            report = json.dumps(replay_recording(recording), sort_keys=True).encode()
            results[name] = {
                "guard": guard,
                "full_parser": parsing,
                "replay_24_frames": measure(replay_recording, recording, 3),
                "replay_sha256": hashlib.sha256(report).hexdigest(),
            }
    finally:
        schema.check_bounds = original
    if len({result["replay_sha256"] for result in results.values()}) != 1:
        raise RuntimeError("replay_parity_failed")
    print(
        json.dumps(
            {
                "qualified": False,
                "compiled": compiled,
                "python": platform.python_version(),
                "os": platform.system(),
                "machine": platform.machine(),
                "results": results,
                "workload_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in workloads.items()},
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
