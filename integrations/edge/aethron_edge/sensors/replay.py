"""Bounded raw sensor replay, with no live-clock admission or semantic inference.

Each record is a big-endian uint32 JSON-header length, UTF-8 header, then
exactly the bytes specified by its validated layout. A stream is one source.
Checksums detect corruption, not authenticity or physical calibration validity.
"""

import hashlib
import json
import struct
from dataclasses import dataclass
from typing import BinaryIO, Literal

from pydantic import Field, model_validator

from .packets import Closed, Cloud, CloudLayout, ImageLayout, Raster, decode_cloud, decode_image

MAX_HEADER = 16384


class Header(Closed):
    version: int = Field(ge=1, le=1)
    source_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    sequence: int = Field(ge=0, le=2**63 - 1)
    acquisition_ns: int = Field(ge=0, le=2**63 - 1)
    clock_domain: Literal["recorded_monotonic"]
    uncertainty_ns: int = Field(ge=0, le=1_000_000_000)
    coordinate_frame: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    modality: Literal["lwir", "nir", "depth", "radar", "lidar"]
    calibration_sha256: str | None = Field(pattern=r"^[0-9a-f]{64}$")
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    layout: ImageLayout | CloudLayout

    @model_validator(mode="after")
    def modality_matches(self):
        if isinstance(self.layout, ImageLayout):
            valid = self.modality == self.layout.modality
        else:
            valid = self.modality in {"radar", "lidar"}
        if not valid:
            raise ValueError("modality_layout_mismatch")
        return self

    @property
    def payload_bytes(self):
        layout = self.layout
        stride = layout.step if isinstance(layout, ImageLayout) else layout.row_step
        return stride * layout.height


@dataclass(frozen=True)
class RecordedFrame:
    header: Header
    payload: Raster | Cloud

    @property
    def live_evidence(self) -> Literal[False]:
        return False


def _read(stream: BinaryIO, size: int, allow_eof=False):
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


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_header_key")
        result[key] = value
    return result


def read_frames(stream: BinaryIO):
    """Yield validated raw frames; retain at most one record, never replay as live."""
    previous = None
    while (prefix := _read(stream, 4, allow_eof=True)) is not None:
        size = struct.unpack(">I", prefix)[0]
        if not 1 <= size <= MAX_HEADER:
            raise ValueError("header_size_limit")
        try:
            value = json.loads(_read(stream, size).decode("utf-8"), object_pairs_hook=_object)
            header = Header.model_validate(value)
        except (UnicodeError, RecursionError) as exc:
            raise ValueError("invalid_header") from exc
        if previous is not None and (
            header.source_id != previous.source_id
            or header.modality != previous.modality
            or header.coordinate_frame != previous.coordinate_frame
            or header.calibration_sha256 != previous.calibration_sha256
            or header.layout != previous.layout
            or header.sequence <= previous.sequence
            or header.acquisition_ns < previous.acquisition_ns
        ):
            raise ValueError("recording_discontinuity")
        data = _read(stream, header.payload_bytes)
        if hashlib.sha256(data).hexdigest() != header.payload_sha256:
            raise ValueError("payload_hash_mismatch")
        decoder = decode_image if isinstance(header.layout, ImageLayout) else decode_cloud
        yield RecordedFrame(header, decoder(header.layout.model_dump(), data))
        previous = header
