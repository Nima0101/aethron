"""Versioned administrator-local raw replay provisioning; never a live clock grant."""

import hashlib
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ..config import strict_json
from ..sources.base import SourceFault
from .packets import Closed
from .provider import GeometryProvider, ProviderCalibration
from .recording_io import MAX_RECORDING_BYTES, recording_frames, regular_file


class ReplayManifest(Closed):
    version: int = Field(ge=1, le=1)
    mode: Literal["recorded"]
    calibration: ProviderCalibration
    indices: tuple[tuple[int, int] | int, ...] = Field(min_length=1, max_length=64)
    valid_for_ns: int = Field(ge=1, le=600_000_000_000)
    loop: bool = False
    recording_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def selection(self):
        if len(set(self.indices)) != len(self.indices):
            raise ValueError("duplicate_sample")
        for index in self.indices:
            if self.calibration.modality == "depth":
                camera = self.calibration.source_camera
                if not isinstance(index, tuple) or not (
                    0 <= index[0] < camera.width and 0 <= index[1] < camera.height
                ):
                    raise ValueError("invalid_pixel")
            elif type(index) is not int or not 0 <= index < 4096:
                raise ValueError("invalid_point_index")
        return self


def load_manifest(path: Path):
    try:
        with regular_file(path, 65536) as stream:
            raw = stream.read(65537)
        strict_json(raw)  # Reject duplicates before strict JSON tuple conversion.
        return ReplayManifest.model_validate_json(raw)
    except (ValueError, TypeError, OSError, RecursionError, OverflowError):
        raise ValueError("invalid_sensor_manifest") from None


@contextmanager
def verified_recording(path, manifest):
    """Validate the full bounded input on the same descriptor used for playback."""
    with regular_file(path, MAX_RECORDING_BYTES) as stream:
        digest = hashlib.sha256()
        total = 0
        for block in iter(lambda: stream.read(65536), b""):
            total += len(block)
            if total > MAX_RECORDING_BYTES:
                raise ValueError("recording_limit")
            digest.update(block)
        if digest.hexdigest() != manifest.recording_sha256:
            raise ValueError("recording_digest")
        stream.seek(0)
        now = 0
        provider = None

        def recording_clock():
            return now

        try:
            for frame in recording_frames(stream):
                now = frame.header.acquisition_ns + frame.header.uncertainty_ns
                if provider is None:
                    provider = GeometryProvider(
                        manifest.calibration,
                        mode="recorded",
                        clock_id="recording",
                        valid_for_ns=manifest.valid_for_ns,
                        clock=recording_clock,
                    )
                result = provider.recorded(
                    frame, manifest.indices, mount_id=manifest.calibration.rig.mount_id
                )
                if isinstance(result, SourceFault):
                    raise ValueError("invalid_recording_geometry")
            stream.seek(0)
            yield stream
        finally:
            if provider is not None:
                provider.close()


def validate_recording(path, manifest):
    with verified_recording(path, manifest):
        pass
