"""Local calibration identity; no implied physical qualification."""

import hashlib
import json
from dataclasses import asdict, dataclass

from .sources.base import FrameEnvelope


@dataclass(frozen=True)
class CalibrationRecord:
    calibration_id: str
    width: int
    height: int
    valid_until_ms: int
    mount_id: str
    transform: tuple[float, ...]
    residual: float

    @property
    def digest(self):
        return hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True, allow_nan=False).encode()
        ).hexdigest()

    def valid_for(self, frame: FrameEnvelope, now_ms: int, mount_id: str) -> bool:
        if any(type(v) is not int or v < 0 for v in (self.valid_until_ms, now_ms)):
            return False
        if any(
            type(v) is not int or v <= 0
            for v in (self.width, self.height, frame.width, frame.height)
        ):
            return False
        if any(
            type(v) is not str or not v
            for v in (self.calibration_id, self.mount_id, frame.calibration_id, mount_id)
        ):
            return False
        if type(self.transform) is not tuple or len(self.transform) != 9:
            return False
        # Keep the record itself JSON-serializable; never normalize its digest inputs.
        if any(type(v) not in (int, float) for v in self.transform) or type(self.residual) not in (
            int,
            float,
        ):
            return False
        return (
            frame.calibration_id == self.calibration_id
            and (frame.width, frame.height) == (self.width, self.height)
            and mount_id == self.mount_id
            and now_ms <= self.valid_until_ms
            # Only already registered normalized coordinates are supported here.
            # A nonidentity transform needs an explicit tested projection adapter.
            and self.transform == (1, 0, 0, 0, 1, 0, 0, 0, 1)
            and 0 <= self.residual <= 0.05
        )
