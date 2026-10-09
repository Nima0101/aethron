"""Supervisor-owned diagnostic telemetry. SPDX-License-Identifier: GPL-3.0-only.

No viewer owns this lifecycle. Protected trust is supplied by the local parent;
restarts never renew authority, provision a journal, or promote measurements.
"""

import multiprocessing as mp
import os
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from multiprocessing.connection import wait

from ..mailbox import Mailbox, StopToken
from .boot_authority import BootClockGuard, BootClockPolicy
from .mavlink import MAX_RECEIVE_AGE_NS, UdpTelemetry
from .signing import SignedTelemetry, SigningTrust

SOURCE_REASONS = frozenset(
    {
        "no_observation",
        "unmapped_source_clock",
        "receive_expired",
        "invalid_packet",
        "unsupported_packet",
        "unsupported_message",
        "sender_mismatch",
        "invalid_values",
        "packet_order",
        "source_clock_reset",
        "local_clock_invalid",
        "closed",
        "signing_authority_expired",
        "signature_time_or_link",
        "invalid_signature",
        "signature_replay",
        "replay_store_failed",
        "worker_fault",
        "clock_authority_rejected",
    }
)


def _peak_ms(previous, elapsed_ns):
    return min(60000, max(previous, (elapsed_ns + 999999) // 1_000_000))


class _MeasuredTelemetry(SignedTelemetry):
    """Wall-time peaks include scheduling; no payloads or timing history retained."""

    def __init__(self, *args, **kwargs):
        self.max_decode_ms = self.max_commit_ms = 0
        super().__init__(*args, **kwargs)

    def _decode_packet(self, packet, now):
        before = time.monotonic_ns()
        try:
            return super()._decode_packet(packet, now)
        finally:
            self.max_decode_ms = _peak_ms(self.max_decode_ms, time.monotonic_ns() - before)

    def _commit_packet(self, packet):
        before = time.monotonic_ns()
        try:
            return super()._commit_packet(packet)
        finally:
            self.max_commit_ms = _peak_ms(self.max_commit_ms, time.monotonic_ns() - before)


@dataclass(frozen=True)
class TelemetryProfile:
    system_id: int
    component_id: int
    port: int
    replay_path: str = field(repr=False)

    def __post_init__(self):
        if (
            any(
                type(x) is not int or not 1 <= x <= 255 for x in (self.system_id, self.component_id)
            )
            or type(self.port) is not int
            or not 0 <= self.port <= 65535
            or type(self.replay_path) is not str
            or not self.replay_path
        ):
            raise ValueError("invalid_telemetry_profile")


def _worker(profile, trust, channel, stop, clock_policy=None):
    # Dependency diagnostics must not expose private paths or key material.
    with open(os.devnull, "wb") as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)

    max_poll_ms = 0

    def emit(state, port=0, samples=0, expires=0, reason="no_observation"):
        try:
            channel.put_nowait(
                {
                    "state": state,
                    "port": port,
                    "samples": samples,
                    "expires_ns": expires,
                    "emitted_ns": time.monotonic_ns(),
                    "source_reason": reason,
                    "max_poll_ms": max_poll_ms,
                    "max_decode_ms": source.max_decode_ms if source is not None else 0,
                    "max_commit_ms": source.max_commit_ms if source is not None else 0,
                }
            )
        except queue.Full:
            pass  # Parent expiry remains authoritative if the slot is unavailable.

    source = None
    try:
        source = _MeasuredTelemetry(
            profile.system_id, profile.component_id, trust=trust, replay_path=profile.replay_path
        )
        guard = (
            BootClockGuard(profile.replay_path, clock_policy, trust)
            if clock_policy is not None
            else None
        )
        with UdpTelemetry(source, port=profile.port) as receiver:
            emit("waiting", receiver.port)
            while not stop.is_set():
                try:
                    authority_until = guard.check() if guard is not None else trust.valid_until_ns
                except ValueError:
                    emit("fault", reason="clock_authority_rejected")
                    return
                before = time.monotonic_ns()
                status = receiver.poll()
                max_poll_ms = _peak_ms(max_poll_ms, time.monotonic_ns() - before)
                if status.reason in {
                    "signing_authority_expired",
                    "local_clock_invalid",
                    "source_clock_reset",
                    "replay_store_failed",
                    "closed",
                }:
                    emit("fault", reason=status.reason)
                    return
                if status.samples and all(sample.authenticated for sample in status.samples):
                    expires = min(
                        authority_until,
                        *(sample.receive_ns + MAX_RECEIVE_AGE_NS for sample in status.samples),
                    )
                    emit(
                        "observed_unverified",
                        receiver.port,
                        len(status.samples),
                        expires,
                        status.reason,
                    )
                else:
                    emit("waiting", receiver.port, reason=status.reason)
    except Exception:
        emit("fault", reason="worker_fault")
    finally:
        if source is not None:
            source.close()


class TelemetrySupervisor:
    """One child and nonblocking latest-status slot, independent of HTTP/UI.

    Spawn/reap happens in the owner thread. Snapshot never waits for native I/O,
    the mailbox lock, process joins or SQLite. Only aggregate state is exported.
    """

    def __init__(self, profile: TelemetryProfile, trust: SigningTrust, *, clock_policy=None):
        if type(profile) is not TelemetryProfile or type(trust) is not SigningTrust:
            raise ValueError("invalid_telemetry_configuration")
        if clock_policy is not None and (
            type(clock_policy) is not BootClockPolicy
            or not trust.boot_bound
            or trust.key != clock_policy.key
            or trust.link_id != clock_policy.link_id
            or (profile.system_id, profile.component_id)
            != (clock_policy.system_id, clock_policy.component_id)
        ):
            raise ValueError("invalid_telemetry_clock_policy")
        self.profile, self.trust = profile, trust
        self.clock_policy = clock_policy
        self.process = None
        self._channel = self._child_stop = None
        self._stop = threading.Event()
        self._thread = None
        self._message = None
        self._fault = None
        self._restarts = 0
        self._attempts = deque(maxlen=5)
        self._next_start = 0
        self._started_ns = 0
        self._last_message_ns = 0
        self._last_now = trust.issued_ns
        self._max_delivery_ms = 0
        self._max_owner_gap_ms = 0
        self._messages_received = self._observed_messages = self._expired_on_arrival = 0
        self._last_tick_ns = None

    def start(self):
        if self._thread is not None or self._stop.is_set():
            raise ValueError("telemetry_already_started")
        self._thread = threading.Thread(target=self._run, name="aethron-telemetry", daemon=True)
        self._thread.start()

    def _valid_time(self, now, last_now):
        return self.trust.issued_ns <= now < self.trust.valid_until_ns and now >= last_now

    def _launch(self):
        ctx = mp.get_context("spawn")
        self._channel, self._child_stop = Mailbox(ctx), StopToken(ctx)
        self._message = None
        self._started_ns = self._last_message_ns = time.monotonic_ns()
        self.process = ctx.Process(
            target=_worker,
            args=(self.profile, self.trust, self._channel, self._child_stop, self.clock_policy),
            daemon=True,
        )
        self.process.start()

    def _retire(self):
        self._message = None
        process = self.process
        if process is None:
            return
        if process.pid is None:
            self.process = None
            return
        self._child_stop.set()
        process.join(timeout=0.2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=0.2)
        if process.is_alive():
            process.kill()
            process.join(timeout=0.2)
        if process.is_alive():
            self._fault = "worker_unreaped"
        else:
            self.process = None

    def _consume(self, now):
        try:
            message = self._channel.get_nowait()
        except queue.Empty:
            return
        now = time.monotonic_ns()  # A child may publish after the owner's tick began.
        fields = {
            "state",
            "port",
            "samples",
            "expires_ns",
            "emitted_ns",
            "source_reason",
            "max_poll_ms",
            "max_decode_ms",
            "max_commit_ms",
        }
        if (
            set(message) != fields
            or message["state"] not in {"waiting", "observed_unverified", "fault"}
            or message["source_reason"] not in SOURCE_REASONS
            or any(type(message[name]) is not int for name in fields - {"state", "source_reason"})
            or not self._started_ns <= message["emitted_ns"] <= now
            or not 0 <= message["port"] <= 65535
            or any(
                not 0 <= message[name] <= 60000
                for name in ("max_poll_ms", "max_decode_ms", "max_commit_ms")
            )
            or not 0 <= message["samples"] <= 2
            or not 0
            <= message["expires_ns"]
            <= min(message["emitted_ns"] + MAX_RECEIVE_AGE_NS, self.trust.valid_until_ns)
        ):
            self._fault = "worker_protocol"
            return
        self._messages_received = min(2**31 - 1, self._messages_received + 1)
        if message["state"] == "observed_unverified" and message["samples"]:
            self._observed_messages = min(2**31 - 1, self._observed_messages + 1)
            if now > message["expires_ns"]:
                self._expired_on_arrival = min(2**31 - 1, self._expired_on_arrival + 1)
        self._last_message_ns = now
        self._max_delivery_ms = _peak_ms(self._max_delivery_ms, now - message["emitted_ns"])
        if message["state"] == "fault":
            self._fault = "worker_fault"
        else:
            self._message = message

    def _run(self):
        try:
            while not self._stop.is_set():
                now = time.monotonic_ns()
                if self._last_tick_ns is not None:
                    self._max_owner_gap_ms = _peak_ms(
                        self._max_owner_gap_ms, now - self._last_tick_ns
                    )
                self._last_tick_ns = now
                if not self._valid_time(now, self._last_now):
                    self._fault = "authority_expired"
                self._last_now = now
                if self._fault:
                    break
                if self.process is None:
                    if now >= self._next_start:
                        self._launch()
                else:
                    self._consume(time.monotonic_ns())
                    if self._fault:
                        break
                    if not self.process.is_alive() or now - self._last_message_ns > 10_000_000_000:
                        self._retire()
                        while self._attempts and now - self._attempts[0] > 60_000_000_000:
                            self._attempts.popleft()
                        if len(self._attempts) == 5:
                            self._fault = "restart_limit"
                            break
                        self._attempts.append(now)
                        self._restarts += 1
                        self._next_start = now + 2_000_000_000
                if self.process is not None:
                    # Observe actual child exit as well as the watchdog interval.
                    # Descriptor waits avoid the coarse condition-timer delays
                    # measured under this Mac launch environment. No priority
                    # changes or freshness extensions are made.
                    wait([self.process.sentinel], timeout=0.01)
                else:
                    self._stop.wait(0.01)
        except Exception:
            self._fault = "worker_fault"
        finally:
            self._retire()

    def snapshot(self):
        last_now = self._last_now
        now = time.monotonic_ns()
        message = self._message
        process = self.process
        state, reason, samples, port = "starting", "source_waiting", 0, 0
        if self._stop.is_set():
            state, reason = "stopped", "closed"
        elif self._fault or not self._valid_time(now, last_now):
            state, reason = "fault", self._fault or "authority_expired"
        elif (
            message is not None
            and process is not None
            and process.is_alive()
            and not wait([process.sentinel], timeout=0)
        ):
            port = message["port"]
            if (
                message["state"] == "observed_unverified"
                and message["samples"]
                and message["emitted_ns"] <= now <= message["expires_ns"]
            ):
                state, reason, samples = (
                    "observed_unverified",
                    "unmapped_source_clock",
                    message["samples"],
                )
            else:
                state = "waiting"
        return {
            "state": state,
            "reason": reason,
            "samples": samples,
            "port": port,
            "authenticated": bool(samples),
            "perception_eligible": False,
            "restarts": self._restarts,
            "source_reason": message["source_reason"] if message is not None else "no_observation",
            "max_poll_ms": message["max_poll_ms"] if message is not None else 0,
            "max_decode_ms": message["max_decode_ms"] if message is not None else 0,
            "max_commit_ms": message["max_commit_ms"] if message is not None else 0,
            "max_delivery_ms": self._max_delivery_ms,
            "max_owner_gap_ms": self._max_owner_gap_ms,
            "messages_received": self._messages_received,
            "observed_messages": self._observed_messages,
            "expired_on_arrival": self._expired_on_arrival,
            "message_age_ms": _peak_ms(0, max(0, now - message["emitted_ns"]))
            if message is not None
            else None,
            "message_state": message["state"] if message is not None else "none",
        }

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        # A failed owner thread must not leave a child behind after shutdown.
        if self._thread is None or not self._thread.is_alive():
            self._retire()
