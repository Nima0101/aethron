"""Bounded health counts in one trusted clock domain; no transport or scene data."""

import json
import threading
from dataclasses import dataclass

_STATES = ("running", "recovering", "fault", "stopped")
_FIELDS = frozenset(("version", "state", "emitted_ms", "status_expires_ms"))
_MAX_TIME = 2**53 - 1


def _valid_time(value):
    return type(value) is int and 0 <= value <= _MAX_TIME


@dataclass(frozen=True)
class _Report:
    state: str
    emitted: int
    expires: int


def _validate(value, now_ms):
    if (
        type(value) is not dict
        or value.keys() != _FIELDS
        or type(value["version"]) is not int
        or value["version"] != 1
        or type(value["state"]) is not str
        or value["state"] not in _STATES
        or not _valid_time(value["emitted_ms"])
        or not _valid_time(value["status_expires_ms"])
        or not _valid_time(now_ms)
        or not value["emitted_ms"] <= now_ms < value["status_expires_ms"]
        or not 1 <= value["status_expires_ms"] - value["emitted_ms"] <= 2000
    ):
        raise ValueError("invalid_health_report")
    return _Report(value["state"], value["emitted_ms"], value["status_expires_ms"])


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("invalid_health_report")
        value[key] = item
    return value


def _invalid_constant(value):
    raise ValueError("invalid_health_report")


def encode_local_health(status: dict, *, now_ms: int) -> bytes:
    """Project a local supervisor snapshot. Never pass remote boot-clock times."""
    if type(status) is not dict:
        raise ValueError("invalid_health_report")
    try:
        value = {key: status[key] for key in _FIELDS}
    except KeyError:
        raise ValueError("invalid_health_report") from None
    _validate(value, now_ms)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class FleetHealth:
    """Fixed authorized slots; caller supplies trusted, same-domain monotonic time.

    Slot authorization, cross-host clock mapping and transport authentication are
    outside this local library. Reports cannot renew their own expiry on receipt.
    """

    def __init__(self, slot_count: int):
        if type(slot_count) is not int or not 1 <= slot_count <= 1024:
            raise ValueError("invalid_health_capacity")
        self._reports: list[_Report | None] = [None] * slot_count
        self._high_water = [-1] * slot_count
        self._now = -1
        self._lock = threading.Lock()

    def _clear(self):
        self._reports[:] = [None] * len(self._reports)

    def _advance(self, now_ms):
        if not _valid_time(now_ms) or now_ms < self._now:
            self._clear()
            raise ValueError("invalid_health_clock")
        self._now = now_ms
        for slot, value in enumerate(self._reports):
            if value is not None and now_ms >= value.expires:
                self._reports[slot] = None

    def ingest(self, slot: int, raw: bytes, *, now_ms: int) -> bool:
        """Rejecting a report withdraws that slot; no input or identifier is echoed."""
        with self._lock:
            self._advance(now_ms)
            if type(slot) is not int or not 0 <= slot < len(self._reports):
                self._clear()
                raise ValueError("invalid_health_slot")
            self._reports[slot] = None
            if type(raw) is not bytes or len(raw) > 256:
                return False
            try:
                value = _validate(
                    json.loads(
                        raw.decode("utf-8"),
                        object_pairs_hook=_pairs,
                        parse_constant=_invalid_constant,
                    ),
                    now_ms,
                )
            except (ValueError, RecursionError):
                return False
            if value.emitted <= self._high_water[slot]:
                return False
            self._high_water[slot] = value.emitted
            self._reports[slot] = value
            return True

    def snapshot(self, *, now_ms: int) -> dict:
        """Export counts only. Missing evidence is unknown, never a safety claim."""
        with self._lock:
            self._advance(now_ms)
            counts = dict.fromkeys((*_STATES, "unknown"), 0)
            for value in self._reports:
                counts["unknown" if value is None else value.state] += 1
            return {
                "version": 1,
                "total": len(self._reports),
                "states": counts,
                "scene_state": "UNKNOWN",
                "qualified": False,
            }
