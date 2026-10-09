"""Conservative exposure-clock admission, independent of wall time."""

from dataclasses import dataclass

from .sources.base import FrameEnvelope, SourceFault


@dataclass(frozen=True)
class MappedFrame:
    frame: FrameEnvelope
    exposure_ns: int
    uncertainty_ns: int


class CaptureClock:
    def __init__(self):
        self.last_sequence = -1
        self.last_capture = -1
        self.clock_id = None

    def map_capture(self, frame: FrameEnvelope, now_ns: int) -> MappedFrame | SourceFault:
        stamp, error = frame.capture_ns, frame.clock_uncertainty_ns
        if any(
            type(value) is not int or value < 0 for value in (stamp, error, frame.sequence, now_ns)
        ):
            return SourceFault("clock_untrusted")
        valid = (
            frame.clock_id == "host_monotonic"
            and stamp is not None
            and error >= 0
            and frame.sequence > self.last_sequence
            and stamp > self.last_capture
            and stamp + error <= now_ns
            and now_ns - stamp + error <= 100_000_000
            and self.clock_id in (None, frame.clock_id)
        )
        self.clock_id = frame.clock_id
        self.last_sequence = frame.sequence
        if stamp is not None:
            self.last_capture = stamp
        if not valid:
            return SourceFault("clock_untrusted")
        return MappedFrame(frame, stamp, error)

    @staticmethod
    def compatible(a_ns, a_error, b_ns, b_error):
        if any(type(value) is not int or value < 0 for value in (a_ns, a_error, b_ns, b_error)):
            return False
        return abs(a_ns - b_ns) + a_error + b_error <= 50_000_000
