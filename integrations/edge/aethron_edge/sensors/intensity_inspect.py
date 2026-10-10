"""Offline intensity inspection; reports are buffered until input validation succeeds."""

import argparse
import hashlib
import json
import re
from pathlib import Path

from ..config import strict_json
from .intensity_replay import IntensityCalibration, rectify_recorded_intensity
from .recording_io import MAX_RECORDING_BYTES, recording_frames, regular_file


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "invalid_intensity_inspection\n")


class _BoundedReader:
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


def main():
    """Emit selected counts and complete source headers after input validation.

    Reports are not anonymized: source aliases, clocks, layouts and digests are
    retained. Buffering prevents reports on input rejection, not partial writes
    if the output destination itself fails. Callers own access and retention.
    """
    parser = _Parser(prog="aethron_edge.sensors.intensity_inspect", description=__doc__)
    parser.add_argument("--recording", required=True, type=Path)
    parser.add_argument("--calibration", required=True, type=Path)
    parser.add_argument("--expected-calibration-sha256", required=True)
    parser.add_argument("--expected-recording-sha256")
    parser.add_argument("--pixel", required=True, action="append", nargs=2, type=int)
    parser.add_argument("--max-frames", type=int, default=1)
    args = parser.parse_args()
    try:
        if (
            not 1 <= args.max_frames <= 300
            or not 1 <= len(args.pixel) <= 64
            or not re.fullmatch(r"[0-9a-f]{64}", args.expected_calibration_sha256)
            or (
                args.expected_recording_sha256 is not None
                and not re.fullmatch(r"[0-9a-f]{64}", args.expected_recording_sha256)
            )
        ):
            raise ValueError("inspection_limit")
        with regular_file(args.calibration, 65536) as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            raise ValueError("calibration_limit")
        strict_json(raw)
        calibration = IntensityCalibration.model_validate_json(raw)
        camera = calibration.lens.output_camera
        if calibration.digest != args.expected_calibration_sha256 or any(
            not (0 <= x < camera.width and 0 <= y < camera.height) for x, y in args.pixel
        ):
            raise ValueError("invalid_selection")
        frames = []
        with regular_file(args.recording, MAX_RECORDING_BYTES) as stream:
            reader = _BoundedReader(stream)
            for index, frame in enumerate(recording_frames(reader)):
                if index >= args.max_frames:
                    raise ValueError("frame_limit")
                result = rectify_recorded_intensity(
                    frame,
                    calibration,
                    expected_calibration_sha256=args.expected_calibration_sha256,
                )
                frames.append(
                    {
                        "source_header": result.source_header.model_dump(),
                        "counts": [result.raster.sample(x, y) for x, y in args.pixel],
                    }
                )
            if (
                args.expected_recording_sha256 is not None
                and reader.digest.hexdigest() != args.expected_recording_sha256
            ):
                raise ValueError("recording_digest")
        print(
            json.dumps(
                {
                    "version": 1,
                    "live_evidence": False,
                    "source_evidence": "recorded",
                    "pixels": args.pixel,
                    "frames": frames,
                },
                separators=(",", ":"),
                allow_nan=False,
            )
        )
    except (ValueError, TypeError, OSError, RecursionError, OverflowError):
        parser.exit(2, "invalid_intensity_inspection\n")


if __name__ == "__main__":
    main()
