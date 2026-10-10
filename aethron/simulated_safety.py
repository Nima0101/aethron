"""Admission of synthetic aggregate declarations; descriptive data, never actuation."""

import json

from ._json_bounds import check as check_bounds
from .actions import recommend
from .schema import CONTRACTS, enum, integer, keys, require, unique_pairs


class DefensiveSimulation:
    """One serialized monotonic synthetic stream under a fixed local contract."""

    def __init__(self, contract):
        enum(contract, CONTRACTS)
        self._contract = contract
        self._now = 0
        self._last = None
        self._reasons = ()
        self._closed = False

    def _clock(self, now):
        try:
            integer(now)
        except ValueError:
            return "invalid_clock"
        if now < self._now:
            return "clock_regression"
        self._now = now
        return None

    def _output(self, *, accepted=False, state="UNKNOWN", until=None):
        return {
            "version": 1,
            "simulation_only": True,
            "motion_authority": False,
            "accepted": accepted,
            "state": state,
            "evidence": "synthetic" if accepted else None,
            "at_ms": self._now,
            "expires_at_ms": self._now if until is None else until,
            "reasons": list(self._reasons),
            **recommend(self._contract, [{"state": "UNKNOWN"}]),
        }

    def _reject(self, reason):
        self._reasons = tuple(sorted(set(self._reasons).union((reason,))))
        return self._output()

    def step(self, data, *, now_ms):
        clock_error = self._clock(now_ms)
        if self._closed:
            return self._reject("closed")
        if clock_error:
            return self._reject(clock_error)
        try:
            require(type(data) is bytes and len(data) <= 2048 and check_bounds(data))
            obj = json.loads(
                data.decode("utf-8"),
                object_pairs_hook=unique_pairs,
                parse_constant=lambda _: require(False),
            )
            keys(obj, "version at_ms expires_at_ms evidence state clock_domain")
            integer(obj["version"], 1, 1)
            integer(obj["at_ms"])
            integer(obj["expires_at_ms"])
            enum(obj["evidence"], ("synthetic",))
            enum(obj["state"], ("PRESENT", "UNKNOWN"))
            enum(obj["clock_domain"], ("host_monotonic_ms",))
        except (ValueError, UnicodeError, RecursionError):
            return self._reject("invalid_input")
        at, until = obj["at_ms"], obj["expires_at_ms"]
        if not (0 <= now_ms - at <= 100 and now_ms < until <= at + 200):
            return self._reject("timestamp")
        if self._last is not None and at <= self._last:
            return self._reject("frame_regression")
        self._last = at
        self._reasons = ()
        # A declaration's larger TTL cannot extend the current-support age bound.
        return self._output(accepted=True, state=obj["state"], until=min(until, at + 100))

    def watchdog(self, *, now_ms):
        clock_error = self._clock(now_ms)
        return self._reject("closed" if self._closed else clock_error or "acquisition_stalled")

    def close(self):
        self._closed = True
        self._reasons = ("closed",)
