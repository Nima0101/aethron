"""Bounded replay I/O comparison; synthetic data, not end-to-end qualification."""

import hashlib
import io
import json
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path

from aethron_edge.sensors import replay
from aethron_edge.sensors.replay import _read

# Both timing and allocation passes require byte-equality assertions.
# Reject optimized imports too, before exposing an unchecked report generator.
if not __debug__:
    raise SystemExit("replay_audit_requires_assertions")


def baseline(stream, size, allow_eof=False):
    buffer = bytearray()
    while len(buffer) < size:
        block = stream.read(size - len(buffer))
        if not isinstance(block, bytes) or len(block) > size - len(buffer):
            raise ValueError("invalid_stream_read")
        if not block:
            if allow_eof and not buffer:
                return None
            raise ValueError("truncated_record")
        buffer.extend(block)
    return bytes(buffer)


def direct(stream, size, allow_eof=False):
    buffer = bytearray()
    while len(buffer) < size:
        block = stream.read(size - len(buffer))
        if not isinstance(block, bytes) or len(block) > size - len(buffer):
            raise ValueError("invalid_stream_read")
        if not block:
            if allow_eof and not buffer:
                return None
            raise ValueError("truncated_record")
        if not buffer and type(block) is bytes and len(block) == size:
            return block
        buffer.extend(block)
    return bytes(buffer)


def readinto(stream, size):
    buffer = bytearray(size)
    offset = 0
    while offset < size:
        count = stream.readinto(memoryview(buffer)[offset:])
        if type(count) is not int or not 0 < count <= size - offset:
            raise ValueError("invalid_stream_read")
        offset += count
    return bytes(buffer)


class Fragmented(io.BytesIO):
    def read(self, size):
        return super().read(min(size, 4096))

    def readinto(self, target):
        return super().readinto(target[:4096])


def main():
    if tracemalloc.is_tracing():
        raise ValueError("replay_audit_tracing_active")
    data = b"x" * (1024 * 1024)
    functions = {"baseline": baseline, "direct": direct, "readinto": readinto, "production": _read}
    report = {
        "source_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in {
                "compare.py": Path(__file__),
                "aethron_edge.sensors.replay": Path(replay.__file__),
            }.items()
        },
        "payload_sha256": hashlib.sha256(data).hexdigest(),
        "payload_bytes": len(data),
        "samples": 15,
        "cases": {},
    }
    with tempfile.TemporaryFile() as file:
        file.write(data)
        for name, stream in (
            ("memory", io.BytesIO(data)),
            ("file", file),
            ("fragmented", Fragmented(data)),
        ):
            samples = {key: {"cpu": [], "wall": [], "peak": []} for key in functions}
            keys = list(functions)
            for iteration in range(15):
                for key in keys[iteration % len(keys) :] + keys[: iteration % len(keys)]:
                    stream.seek(0)
                    cpu, wall = time.process_time_ns(), time.perf_counter_ns()
                    result = functions[key](stream, len(data))
                    samples[key]["cpu"].append((time.process_time_ns() - cpu) / 1e6)
                    samples[key]["wall"].append((time.perf_counter_ns() - wall) / 1e6)
                    assert result == data
                    del result
                    stream.seek(0)
                    tracemalloc.start()
                    try:
                        result = functions[key](stream, len(data))
                        samples[key]["peak"].append(tracemalloc.get_traced_memory()[1])
                    finally:
                        tracemalloc.stop()
                    assert result == data
                    del result
            report["cases"][name] = {
                key: {
                    "cpu_p50_ms": statistics.median(s["cpu"]),
                    "wall_p50_ms": statistics.median(s["wall"]),
                    "traced_peak_bytes": max(s["peak"]),
                }
                for key, s in samples.items()
            }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
