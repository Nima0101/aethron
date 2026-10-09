"""Whole stateful-clock diagnostic comparison, not latency qualification."""

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import platform
import statistics
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

from aethron_edge import timebase
from aethron_edge.sources.base import FrameEnvelope


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args()
    native = any(str(timebase.__file__).endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES)
    if args.require_native and not native:
        raise RuntimeError("native_clock_required")
    source = Path(timebase.__file__).with_name("timebase.py")
    spec = importlib.util.spec_from_file_location("aethron_edge._clock_reference", source)
    reference = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = reference
    spec.loader.exec_module(reference)
    clocks = {"python_reference": reference.CaptureClock, "installed": timebase.CaptureClock}
    frames = [
        FrameEnvelope(
            b"\0" * 3, 1, 1, i, i * 1_000_000, 1_000_000_000, "host_monotonic", 0, "bench"
        )
        for i in range(901, 1001)
    ]
    cases = [(frame, frame.capture_ns) for frame in frames]
    cases += [(frames[-2], 1_000_000_000), (frames[-1], 1_000_000_000)]
    cases += [(replace(frames[-1], sequence=1001, capture_ns=1_000_000_001), 1_000_000_001)]
    for field in ("capture_ns", "clock_uncertainty_ns", "sequence"):
        cases += [
            (replace(frames[-1], **{field: v}), 1_000_000_000) for v in (True, -1, None, 0.5, "0")
        ]
    cases += [(frames[-1], v) for v in (True, -1, None, 0.5, "0")]
    cases += [(replace(frames[-1], sequence=2000, capture_ns=2**100), 2**100)]
    reports = {}
    for name, clock_type in clocks.items():
        clock = clock_type()
        trace = []
        for frame, now in cases:
            result = clock.map_capture(frame, now)
            trace.append((type(result).__name__, asdict(result), vars(clock)))
            # Snapshot state: later calls must not rewrite earlier trace entries.
            trace[-1] = (*trace[-1][:-1], dict(trace[-1][-1]))
        reports[name] = hashlib.sha256(repr(trace).encode()).hexdigest()
    if len(set(reports.values())) != 1:
        raise RuntimeError("stateful_clock_parity_failed")
    samples = {name: [] for name in clocks}
    for batch in range(5):
        for name in list(clocks)[:: 1 if batch % 2 else -1]:
            start = time.process_time_ns()
            for _ in range(100):
                clock = clocks[name]()
                for frame, now in cases:
                    clock.map_capture(frame, now)
            samples[name].append((time.process_time_ns() - start) / (100 * len(cases)))
    print(
        json.dumps(
            {
                "qualified": False,
                "python": platform.python_version(),
                "platform": platform.platform(),
                "native_installed": native,
                "cases": len(cases),
                "trace_sha256": reports,
                "cpu_ns_per_call": samples,
                "median_cpu_ns_per_call": {k: statistics.median(v) for k, v in samples.items()},
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
