"""Bounded passive MAVLink 2 observations. SPDX-License-Identifier: GPL-3.0-only.

No transmitter, command microservice, capture-clock mapping or evidence authority.
Each datagram must contain exactly one allowlisted common-dialect packet.
Sender IDs filter routing; they are not authentication. Never feed these values
to perception/ego compensation without a separately qualified clock/registration.
"""

import math
import socket
import time
from dataclasses import dataclass
from importlib.metadata import version
from typing import Literal

MAX_PACKET = 280
MAX_RECEIVE_AGE_NS = 100_000_000
_LAYOUTS = {
    30: (
        "ATTITUDE",
        "body_euler",
        ("roll", "pitch", "yaw", "rollspeed", "pitchspeed", "yawspeed"),
        ("rad", "rad", "rad", "rad/s", "rad/s", "rad/s"),
    ),
    32: (
        "LOCAL_POSITION_NED",
        "local_ned_unregistered",
        ("x", "y", "z", "vx", "vy", "vz"),
        ("m", "m", "m", "m/s", "m/s", "m/s"),
    ),
}


@dataclass(frozen=True)
class Observation:
    system_id: int
    component_id: int
    message: str
    frame: str
    fields: tuple[str, ...]
    values: tuple[float, ...]
    units: tuple[str, ...]
    source_boot_ms: int
    receive_ns: int
    capture_ns: None = None
    evidence: Literal["external_unverified"] = "external_unverified"
    authenticated: bool = False
    link_id: int | None = None
    signature_timestamp: int | None = None


@dataclass(frozen=True)
class TelemetryStatus:
    state: Literal["UNKNOWN", "OBSERVED_UNVERIFIED"]
    reason: str
    samples: tuple[Observation, ...] = ()
    perception_eligible: Literal[False] = False


class PassiveTelemetry:
    """Two latest-only slots; single-owner/thread API, no stored trajectory.

    Only local monotonic receipt age is known, never physical measurement age.
    Duplicate/reordered sequence packets withdraw observations. Remote boot-time
    rollback/wrap or local clock rollback latches UNKNOWN until a new instance.
    Unsigned traffic cannot provide replay protection or authenticated provenance.
    """

    _signature_bytes = 0

    def __init__(self, system: int, component: int, *, clock=time.monotonic_ns):
        if any(type(x) is not int or not 1 <= x <= 255 for x in (system, component)):
            raise ValueError("invalid_sender")
        # Import only when this optional adapter is instantiated. MAVLink(None)
        # has no writer; no mavutil connection/automatic message sender is used.
        from pymavlink.dialects.v20 import common

        if version("pymavlink") != "2.4.50" or common.MAVLINK_IGNORE_CRC:
            raise ValueError("unsafe_mavlink_sdk")
        self._decoder = common.MAVLink(None)
        self._common = common
        self._decode_error = common.MAVError
        self._system, self._component = system, component
        self._clock = clock
        self._last_now = None
        self._sequence = None
        self._boot = {}
        self._samples = {}
        self._reason = "no_observation"
        self._latched = False

    def _withdraw(self, reason, *, latch=False):
        self._samples.clear()
        self._reason = reason
        self._latched = self._latched or latch

    def _now(self):
        if self._latched:
            return None
        try:
            now = self._clock()
        except BaseException:
            # Withdraw before propagating, including operator interruption/exit.
            # A recovered clock must not revive samples from the failed session.
            self._withdraw("local_clock_invalid", latch=True)
            raise
        if type(now) is not int or now < 0 or (self._last_now is not None and now < self._last_now):
            self._withdraw("local_clock_invalid", latch=True)
            return None
        self._last_now = now
        return now if self._authority_valid(now) else None

    def _authority_valid(self, now):
        return True

    def _decode_packet(self, packet, now):
        return self._decoder.decode(bytearray(packet))

    def _commit_packet(self, packet):
        return True

    def ingest(self, packet: bytes) -> None:
        now = self._now()
        if now is None:
            return
        if type(packet) is not bytes or not 12 <= len(packet) <= MAX_PACKET:
            self._withdraw("invalid_packet")
            return
        if packet[0] != 0xFD or packet[2] != bool(self._signature_bytes) or packet[3] != 0:
            # No signed/unsigned downgrade or unknown flag negotiation.
            self._withdraw("unsupported_packet")
            return
        if len(packet) != packet[1] + 12 + self._signature_bytes:
            self._withdraw("invalid_packet")
            return
        message_id = int.from_bytes(packet[7:10], "little")
        if message_id not in _LAYOUTS:
            self._withdraw("unsupported_message")
            return
        if not 1 <= packet[1] <= 28:
            # Both pinned messages have 28-byte payloads with no extensions;
            # MAVLink 2 may trim trailing zeros, but must retain one byte.
            self._withdraw("invalid_packet")
            return
        if (packet[5], packet[6]) != (self._system, self._component):
            self._withdraw("sender_mismatch")
            return
        try:
            message = self._decode_packet(packet, now)
        except self._decode_error:
            self._withdraw("invalid_packet")
            return
        except BaseException:
            # Unexpected SDK failure or interruption invalidates this session.
            # Withdraw before propagating; later calls must not revive old data.
            self._withdraw("decoder_fault", latch=True)
            raise
        if message is None:
            return
        name, frame, fields, units = _LAYOUTS[message_id]
        try:
            values = tuple(float(getattr(message, field)) for field in fields)
            if not all(math.isfinite(value) for value in values):
                self._withdraw("invalid_values")
                return
            boot = message.time_boot_ms
        except BaseException:
            # SDK field access/conversion is part of decoding too. A failure
            # must not leave observations from before this failed attempt live.
            self._withdraw("decoder_fault", latch=True)
            raise
        try:
            sequence = packet[4]
            if self._sequence is not None and not 1 <= (sequence - self._sequence) % 256 <= 127:
                self._withdraw("packet_order")
                return
            if message_id in self._boot and boot <= self._boot[message_id]:
                # Identical acquisition timestamps are replay/duplicates, not a new
                # observation; reset/wrap needs explicit fresh session provisioning.
                self._withdraw("source_clock_reset", latch=True)
                return
            if not self._commit_packet(packet):
                return
            self._sequence = sequence
            self._boot[message_id] = boot
            self._samples[message_id] = Observation(
                self._system,
                self._component,
                name,
                frame,
                fields,
                values,
                units,
                boot,
                now,
                authenticated=bool(self._signature_bytes),
                link_id=packet[-13] if self._signature_bytes else None,
                signature_timestamp=int.from_bytes(packet[-12:-6], "little")
                if self._signature_bytes
                else None,
            )
            self._reason = "unmapped_source_clock"
        except BaseException:
            # Publication may fail after replay state or local counters advance.
            # Withdraw and require a fresh session; never roll durable state back.
            self._withdraw("state_commit_fault", latch=True)
            raise

    def snapshot(self) -> TelemetryStatus:
        now = self._now()
        if now is not None:
            stale = [
                key
                for key, value in self._samples.items()
                if now - value.receive_ns > MAX_RECEIVE_AGE_NS
            ]
            for key in stale:
                del self._samples[key]
            if stale and not self._samples:
                self._reason = "receive_expired"
        samples = tuple(self._samples[key] for key in sorted(self._samples))
        return TelemetryStatus(
            "OBSERVED_UNVERIFIED" if samples else "UNKNOWN", self._reason, samples
        )

    def close(self) -> None:
        self._withdraw("closed", latch=True)
        self._boot.clear()
        self._sequence = None


class UdpTelemetry:
    """Loopback-only receive socket for a local simulator/operator-owned router.

    One bounded datagram per poll; no ACK, TIMESYNC, heartbeat or command send.
    No background thread or WAN dependency. Socket timeouts still expire state.
    This is diagnostic receipt freshness, not a bound on router/kernel queue age.
    """

    def __init__(self, source: PassiveTelemetry, *, port: int):
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
            packet = self._socket.recv(MAX_PACKET + 1)
        except socket.timeout:
            pass
        except OSError:
            self.close()
        else:
            self._source.ingest(packet)
        return self._source.snapshot()

    def close(self):
        self._socket.close()
        self._source.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
