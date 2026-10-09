"""Bounded, receive-only MAVLink 2 batches. SPDX-License-Identifier: GPL-3.0-only.

Opt-in v1 transport contract; existing single-packet interfaces are unchanged.
Synthetic/router integration only, with no capture-clock or perception authority.
"""

import socket
import time

from .mavlink import MAX_PACKET, MAX_RECEIVE_AGE_NS, PassiveTelemetry, TelemetryStatus

MAX_PACKETS = 16
MAX_DATAGRAM = MAX_PACKETS * MAX_PACKET


def _packets(data):
    if type(data) is not bytes or not 12 <= len(data) <= MAX_DATAGRAM:
        return None
    packets = []
    offset = 0
    while offset < len(data):
        if len(packets) == MAX_PACKETS or len(data) - offset < 12:
            return None
        if data[offset] != 0xFD or data[offset + 2] not in (0, 1) or data[offset + 3] != 0:
            return None
        end = offset + 12 + data[offset + 1] + (13 if data[offset + 2] else 0)
        if end > len(data):
            return None
        packets.append(data[offset:end])
        offset = end
    return packets


class DatagramTelemetryV1:
    """Exclusively owns a decoder; single owner/thread, no concurrent access.

    Framing is checked before any packet is consumed. Semantic failures stop the
    batch and withdraw samples; already committed replay counters stay committed.
    Each framed batch replaces previous samples, preserving receipt deadlines.
    Inject the same trusted monotonic clock into this wrapper and its decoder.
    """

    def __init__(self, source: PassiveTelemetry, *, clock=time.monotonic_ns):
        if not isinstance(source, PassiveTelemetry):
            raise ValueError("invalid_telemetry_source")
        self._source = source
        self._clock = clock
        self._last_now = None
        self._expires = None
        self._reason = None
        self._closed = False

    def _now(self):
        if self._closed:
            return None
        now = self._clock()
        if type(now) is not int or now < 0 or (self._last_now is not None and now < self._last_now):
            self.close()
            self._reason = "local_clock_invalid"
            return None
        self._last_now = now
        return now

    def _withdraw(self, reason):
        # Use the public invalid-input path, preserving decoder high-water marks.
        self._source.ingest(b"")
        self._expires = None
        self._reason = reason

    def ingest(self, data: bytes) -> None:
        now = self._now()
        if now is None:
            return
        packets = _packets(data)
        if packets is None:
            self._withdraw("invalid_datagram")
            return
        # Never carry a previous batch's delayed sample into a new deadline.
        # Invalid input clears samples without resetting replay/order counters.
        self._source.ingest(b"")
        self._reason = None
        self._expires = now + MAX_RECEIVE_AGE_NS
        for packet in packets:
            self._source.ingest(packet)
            if self.snapshot().state == "UNKNOWN":
                # Preserve the rejection reason during subsequent silence.
                self._expires = None
                return

    def snapshot(self) -> TelemetryStatus:
        now = self._now()
        if now is not None and self._expires is not None and now > self._expires:
            self._withdraw("datagram_expired")
        if self._reason is not None:
            return TelemetryStatus("UNKNOWN", self._reason)
        return self._source.snapshot()

    def close(self) -> None:
        self._closed = True
        self._expires = None
        self._reason = "closed"
        self._source.close()


class UdpTelemetryV1:
    """One loopback datagram per poll, <=20 ms socket wait, never transmits."""

    def __init__(self, source: DatagramTelemetryV1, *, port: int):
        if not isinstance(source, DatagramTelemetryV1):
            raise ValueError("invalid_datagram_source")
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("invalid_port")
        self._source = source
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self._socket.settimeout(0.02)
            self._socket.bind(("127.0.0.1", port))
            self.port = self._socket.getsockname()[1]
        except OSError:
            self._socket.close()
            raise OSError("telemetry_bind_failed") from None

    def poll(self) -> TelemetryStatus:
        try:
            data = self._socket.recv(MAX_DATAGRAM + 1)
        except socket.timeout:
            pass
        except OSError:
            self.close()
        else:
            self._source.ingest(data)
        return self._source.snapshot()

    def close(self) -> None:
        self._socket.close()
        self._source.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
