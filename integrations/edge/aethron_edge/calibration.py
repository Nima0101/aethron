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
