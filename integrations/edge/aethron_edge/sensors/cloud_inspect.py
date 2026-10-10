"""Bounded offline raw cloud inspection; no registration, classes or live evidence."""

import argparse
import hashlib
import json
import re
from pathlib import Path

from .packets import MAX_POINTS, Cloud
from .recording_io import MAX_RECORDING_BYTES, recording_frames, regular_file


class _DigestReader:
    """Hash exactly the consumed bytes, including a size check if the file grows."""

    def __init__(self, stream):
        self.stream = stream
        self.total = 0
        self.digest = hashlib.sha256()

    def read(self, size):
        block = self.stream.read(min(size, MAX_RECORDING_BYTES - self.total + 1))
        self.total += len(block)
        if self.total > MAX_RECORDING_BYTES:
            raise ValueError("recording_limit")
        self.digest.update(block)
        return block


def inspect_recording(path, *, expected_sha256, indices, max_frames=1):
    """Return selected raw samples only after full validation and digest agreement.

    Missing or nonfinite samples are None. Indices refer to packet ordinals, not
    objects, and never establish correspondence between frames. A calibration
    digest in a source header is retained metadata, not verified registration.
    """
    try:
        if (
            type(expected_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
            or type(max_frames) is not int
            or not 1 <= max_frames <= 300
            or not isinstance(indices, (list, tuple))
            or not 1 <= len(indices) <= 64
            or any(type(i) is not int or not 0 <= i < MAX_POINTS for i in indices)
            or len(set(indices)) != len(indices)
        ):
            raise ValueError("inspection_limit")
        selected = list(indices)
        frames = []
        with regular_file(path, MAX_RECORDING_BYTES) as stream:
            reader = _DigestReader(stream)
            for index, frame in enumerate(recording_frames(reader)):
                if index >= max_frames or not isinstance(frame.payload, Cloud):
                    raise ValueError("unsupported_recording")
                payload = frame.payload
                samples = []
                for ordinal in selected:
                    point = (
                        payload.sample_points[ordinal]
                        if ordinal < len(payload.sample_points)
                        else None
                    )
                    samples.append(
                        None
                        if point is None
                        else {
                            "xyz_m": list(point.xyz_m),
                            "radial_velocity_mps": point.radial_velocity_mps,
                        }
                    )
                frames.append(
                    {
                        "source_header": frame.header.model_dump(),
                        "sample_count": len(payload.sample_points),
                        "invalid_sample_count": payload.invalid_points,
                        "samples": samples,
                    }
                )
            if reader.digest.hexdigest() != expected_sha256:
                raise ValueError("recording_digest")
        return {
            "version": 1,
            "source_evidence": "recorded",
            "live_evidence": False,
            "registered": False,
            "state": "UNKNOWN",
            "recording_sha256": expected_sha256,
            "indices": selected,
            "frames": frames,
        }
    except (ValueError, TypeError, OSError, RecursionError, OverflowError):
        raise ValueError("invalid_cloud_inspection") from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "invalid_cloud_inspection\n")


def main():
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--recording", required=True, type=Path)
    parser.add_argument("--expected-recording-sha256", required=True)
    parser.add_argument("--index", required=True, action="append", type=int)
    parser.add_argument("--max-frames", type=int, default=1)
    args = parser.parse_args()
    try:
        report = inspect_recording(
            args.recording,
            expected_sha256=args.expected_recording_sha256,
            indices=args.index,
            max_frames=args.max_frames,
        )
        print(json.dumps(report, separators=(",", ":"), allow_nan=False))
    except (ValueError, OSError):
        parser.exit(2, "invalid_cloud_inspection\n")


if __name__ == "__main__":
    main()
