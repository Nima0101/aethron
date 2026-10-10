"""Bounded opaque software-artifact buffering; admission never establishes trust."""

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional

from .passports import _integer, _require, _token


@dataclass(frozen=True)
class InboxResult:
    status: str
    reason: str
    items: int
    payload_bytes: int
    peer: Optional[str] = None
    payload: Optional[bytes] = field(default=None, repr=False)
    expires_at_ms: Optional[int] = None
    execution_authority: bool = field(default=False, init=False)
    motion_authority: bool = field(default=False, init=False)
    evidence_verified: bool = field(default=False, init=False)


class BoundedInbox:
    """Caller-clocked, process-local FIFO with atomic quota and expiry updates."""

    def __init__(self, *, max_items=16, max_bytes=1048576, max_per_peer=16):
        try:
            for value in (max_items, max_bytes, max_per_peer):
                _integer(value, 1)
            _require(max_items <= 16 and max_bytes <= 1048576)
            _require(max_per_peer <= max_items)
        except ValueError:
            raise ValueError("invalid_limits") from None
        self._max_items = max_items
        self._max_bytes = max_bytes
        self._max_per_peer = max_per_peer
        self._entries = deque()
        self._bytes = 0
        self._last_time = 0
        self._closed = False
        self._lock = Lock()

    def _result(self, status, reason, entry=None):
        return InboxResult(
            status,
            reason,
            len(self._entries),
            self._bytes,
            *(entry if entry is not None else (None, None, None)),
        )

    def _advance(self, now_ms):
        if self._closed:
            return "closed"
        try:
            _integer(now_ms)
            _require(now_ms >= self._last_time)
        except ValueError:
            self._entries.clear()
            self._bytes = 0
            self._closed = True
            return "clock_fault"
        self._last_time = now_ms
        # Deadlines need not be ordered; expiring only the head leaks capacity.
        self._entries = deque(entry for entry in self._entries if now_ms < entry[2])
        self._bytes = sum(len(entry[1]) for entry in self._entries)
        return None

    def put(self, peer, payload, *, now_ms, expires_at_ms):
        with self._lock:
            fault = self._advance(now_ms)
            if fault:
                return self._result("rejected", fault)
            try:
                _token(peer)
                _require(type(payload) is bytes and 1 <= len(payload) <= 65536)
                _integer(expires_at_ms)
                _require(now_ms < expires_at_ms <= now_ms + 60000)
            except ValueError:
                return self._result("rejected", "invalid_input")
            if len(self._entries) >= self._max_items:
                return self._result("rejected", "item_capacity")
            if self._bytes + len(payload) > self._max_bytes:
                return self._result("rejected", "byte_capacity")
            if sum(entry[0] == peer for entry in self._entries) >= self._max_per_peer:
                return self._result("rejected", "peer_capacity")
            self._entries.append((peer, payload, expires_at_ms))
            self._bytes += len(payload)
            return self._result("queued", "resource_admitted")

    def take(self, *, now_ms):
        with self._lock:
            fault = self._advance(now_ms)
            if fault:
                return self._result("rejected", fault)
            if not self._entries:
                return self._result("empty", "no_current_entry")
            entry = self._entries.popleft()
            self._bytes -= len(entry[1])
            return self._result("dequeued", "requires_verification", entry)

    def close(self):
        with self._lock:
            self._entries.clear()
            self._bytes = 0
            self._closed = True
