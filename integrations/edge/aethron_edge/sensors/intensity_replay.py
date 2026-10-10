"""Calibration-bound recorded intensity remapping; no authenticity or live grant."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal

from pydantic import Field, model_validator

from .packets import Closed, ImageLayout, Raster, decode_image
from .raster_rectification import (
    MAX_OUTPUT_PIXELS,
    RectifiedMono8,
    RectifiedMono16,
    rectify_mono8_recorded,
    rectify_mono16_recorded,
)
from .rectification import FisheyeCalibration, LensCalibration
from .replay import Header, RecordedFrame


class IntensityCalibration(Closed):
    version: int = Field(ge=1, le=1)
    source_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    coordinate_frame: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    layout: ImageLayout
    lens: LensCalibration | FisheyeCalibration

    @model_validator(mode="after")
    def intensity_geometry(self):
        camera, output = self.lens.camera, self.lens.output_camera
        if (
            self.layout.modality not in {"lwir", "nir"}
            or (self.layout.width, self.layout.height) != (camera.width, camera.height)
            or output.width * output.height > MAX_OUTPUT_PIXELS
        ):
            raise ValueError("invalid_intensity_calibration")
        return self

    @property
    def digest(self):
        document = json.dumps(
            self.model_dump(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        return hashlib.sha256(b"aethron-recorded-intensity-v1\n" + document).hexdigest()


@dataclass(frozen=True)
class RecordedIntensity:
    # The header describes the original raw recording, NOT the remapped raster.
    source_header: Header = field(repr=False)
    calibration: IntensityCalibration = field(repr=False)
    raster: RectifiedMono8 | RectifiedMono16 = field(repr=False)

    @property
    def version(self) -> Literal[1]:
        return 1

    @property
    def source_evidence(self) -> Literal["recorded"]:
        return "recorded"

    @property
    def live_evidence(self) -> Literal[False]:
        return False


def rectify_recorded_intensity(frame, calibration, *, expected_calibration_sha256):
    """Match an independently supplied pin before remapping one recorded frame.

    The pin establishes equality only, not signature verification or physical
    calibration validity. No clock conversion, freshness renewal or history is
    introduced. Sequence/clock continuity remains the replay reader's contract.
    Repeated calls do not establish freshness or reject duplicates. The returned
    source header describes raw input bytes and layout, not the remapped output.
    Source aliases and matching pins do not authenticate a physical device.
    """
    try:
        if (
            type(frame) is not RecordedFrame
            or type(frame.header) is not Header
            or type(frame.payload) is not Raster
            or type(calibration) is not IntensityCalibration
            or type(expected_calibration_sha256) is not str
        ):
            raise ValueError("unsupported_input")
        # Reconstruct nested models too: model_copy/model_construct can bypass
        # validation even on frozen Pydantic objects supplied by Python callers.
        calibration = IntensityCalibration.model_validate(calibration.model_dump())
        header = Header.model_validate(frame.header.model_dump())
        payload = decode_image(frame.payload.layout.model_dump(), frame.payload.data)
        if (
            calibration.digest != expected_calibration_sha256
            or header.calibration_sha256 != expected_calibration_sha256
            or header.source_id != calibration.source_id
            or header.coordinate_frame != calibration.coordinate_frame
            or header.layout != calibration.layout
            or payload.layout != calibration.layout
            or hashlib.sha256(payload.data).hexdigest() != header.payload_sha256
        ):
            raise ValueError("recording_binding_mismatch")
        remap = (
            rectify_mono8_recorded
            if payload.layout.encoding == "mono8"
            else rectify_mono16_recorded
        )
        return RecordedIntensity(header, calibration, remap(payload, calibration.lens))
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ValueError("invalid_intensity_replay") from None
