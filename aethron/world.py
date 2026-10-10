"""Bounded scene model over v3 fusion; no physical transforms or persistent identities."""

from .actions import recommend
from .schema import integer, parse, require
from .temporal import Session

COORDINATE_FRAME = "registered_image_normalized"
CLOCK_DOMAIN = "host_monotonic_ms"


class WorldModel:
    """One serialized upstream scene with explicit frame/clock declarations.

    Call watchdog on acquisition stalls and close on exit. All adapter times must
    already use the same trusted host epoch. Metadata labels do not prove that.
    Outputs retain v3 deadlines; never record or correlate ephemeral track IDs.
    """

    def __init__(self):
        self._session = Session()
        self._now = 0
        self._frame_at = None
        self._contract = "warn"
        self._reasons = ()
        self._quarantined = False
        self._closed = False

    def _clock(self, now_ms):
        try:
            integer(now_ms)
        except ValueError:
            return "invalid_clock"
        if now_ms < self._now:
            return "clock_regression"
        self._now = now_ms
        return None

    def _envelope(self, scene):
        return {
            "world_model_version": 1,
            "coordinate_frame": COORDINATE_FRAME,
            "clock_domain": CLOCK_DOMAIN,
            "quarantined": self._quarantined,
            "scene": scene,
        }

    def _unknown(self):
        return self._envelope(
            {
                "version": 3,
                "at_ms": self._now,
                "evidence": None,
                "state": "UNKNOWN",
                "tracks": [],
                "reasons": list(self._reasons),
                "expires_at_ms": self._now,
                "recommendation": recommend(self._contract, [{"state": "UNKNOWN"}]),
            }
        )

    def _quarantine(self, reason):
        self._session.close()
        self._session = Session()
        self._quarantined = True
        # Only fixed core/boundary codes enter this set; repeated faults cannot
        # grow a history or erase a known sensor failure before fresh evidence.
        self._reasons = tuple(sorted(set(self._reasons).union((reason,))))
        return self._unknown()

    def step(self, data, *, now_ms, coordinate_frame, clock_domain):
        """Consume strict v3 bytes; rejected payloads are cleared, never retained."""
        clock_error = self._clock(now_ms)
        if self._closed:
            return self._quarantine("closed")
        if clock_error:
            return self._quarantine(clock_error)
        if type(coordinate_frame) is not str or coordinate_frame != COORDINATE_FRAME:
            return self._quarantine("unsupported_coordinate_frame")
        if type(clock_domain) is not str or clock_domain != CLOCK_DOMAIN:
            return self._quarantine("unsupported_clock_domain")
        try:
            f = parse(data)
            require(f["version"] == 3)
        except ValueError:
            return self._quarantine("invalid_input")
        at = f["at_ms"]
        if not 0 <= now_ms - at <= 100:
            return self._quarantine("frame_timestamp")
        if self._frame_at is not None and at <= self._frame_at:
            return self._quarantine("frame_regression")
        scene = self._session.step(data, now_ms=now_ms)
        if "invalid_input" in scene["reasons"]:
            return self._quarantine("invalid_input")
        self._frame_at = at
        self._contract = f["contract"]
        self._reasons = tuple(scene["reasons"])
        self._quarantined = False
        return self._envelope(scene)

    def watchdog(self, *, now_ms):
        """Withdraw all current evidence on a stall, retaining bounded diagnostics."""
        clock_error = self._clock(now_ms)
        if self._closed:
            return self._quarantine("closed")
        if clock_error:
            return self._quarantine(clock_error)
        if self._quarantined:
            return self._unknown()
        scene = self._session.watchdog(now_ms=now_ms)
        scene["reasons"] = sorted(set(scene["reasons"]).union(self._reasons))
        return self._envelope(scene)

    def close(self):
        """Erase linkage and permanently close this model."""
        self._session.close()
        self._closed = True
        self._quarantined = True
        self._reasons = ("closed",)
