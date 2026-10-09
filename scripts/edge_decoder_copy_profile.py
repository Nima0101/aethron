#!/usr/bin/env python3
"""Diagnostic shared-buffer copy comparison; no camera/RSS/latency qualification."""

import hashlib
import json
import multiprocessing as mp
import platform
import statistics
import time
import tracemalloc
from pathlib import Path

from aethron_edge.sources.base import MAX_RAW, SourceConfig
from aethron_edge.sources.file import FileSource


def main():
    ctx = mp.get_context("spawn")
    source = FileSource()
    source.slot = ctx.RawArray("B", MAX_RAW)
    source.metadata = ctx.RawArray("q", 4)
    source.lock = ctx.Lock()
    source.config = SourceConfig("file", "synthetic", "ffmpeg", "bench")
    expected = bytes(range(256)) * (MAX_RAW // 256)
    memoryview(source.slot).cast("B")[:] = expected

    def admitted_copy():
        source.metadata[:] = [source.last_sequence + 1, 1920, 1080, 1234]
        frame = source.read(time.monotonic_ns() + 5_000_000_000)
        return frame.pixels

    gates = {
        "previous_boxed_copy": lambda: bytes(source.slot[:MAX_RAW]),
        "admitted_buffer_copy": admitted_copy,
    }
    samples = {name: [] for name in gates}
    for batch in range(5):
        for name in list(gates)[:: 1 if batch % 2 else -1]:
            start = time.process_time_ns()
            pixels = gates[name]()
            samples[name].append(time.process_time_ns() - start)
            if pixels != expected:
                raise RuntimeError("decoder_copy_parity_failed")
            del pixels
    peaks = {}
    for name, gate in gates.items():
        tracemalloc.start()
        pixels = gate()
        _, peaks[name] = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        if pixels != expected:
            raise RuntimeError("decoder_copy_parity_failed")
        del pixels
    # Producer-side copy only; real _decode publication parity is tested separately.
    write_samples = {"ctypes_slice": [], "native_buffer": []}
    for batch in range(5):
        for name in list(write_samples)[:: 1 if batch % 2 else -1]:
            memoryview(source.slot).cast("B")[:] = bytes(MAX_RAW)
            start = time.process_time_ns()
            if name == "ctypes_slice":
                source.slot[:MAX_RAW] = expected
            else:
                memoryview(source.slot).cast("B")[:] = expected
            write_samples[name].append(time.process_time_ns() - start)
            if memoryview(source.slot).cast("B") != expected:
                raise RuntimeError("decoder_write_parity_failed")
    root = Path(__file__).resolve().parents[1]
    print(
        json.dumps(
            {
                "qualified": False,
                "python": platform.python_version(),
                "platform": platform.platform(),
                "input_bytes": len(expected),
                "input_sha256": hashlib.sha256(expected).hexdigest(),
                "cpu_ns": samples,
                "median_cpu_ns": {k: statistics.median(v) for k, v in samples.items()},
                "python_traced_peak_bytes": peaks,
                "producer_copy_cpu_ns": write_samples,
                "producer_copy_median_cpu_ns": {
                    name: statistics.median(values) for name, values in write_samples.items()
                },
                "source_sha256": {
                    p: hashlib.sha256((root / p).read_bytes()).hexdigest()
                    for p in (
                        "integrations/edge/aethron_edge/sources/base.py",
                        "scripts/edge_decoder_copy_profile.py",
                    )
                },
            },
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
