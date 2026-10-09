# Passive MAVLink datagram adapter v1

Scope: software-only P3.1 local-router/simulation integration. This opt-in
transport wrapper does not change the single-packet decoder or any P2 interface.
It does not qualify PX4, ArduPilot, physical firmware or hardware timing.

## Technology decision — 2026-10-09

Requirements: bounded concatenated MAVLink 2 framing, existing signed replay
protection, no transmitter, no new perception authority, portable focused tests.
The official [serialization specification](https://mavlink.io/en/guide/serialization.html)
defines a 10-byte header, payload length, 2-byte CRC and optional 13-byte signature.
The [Python dialect API](https://mavlink.io/en/mavgen_python/) permits a decoder
without a connection/writer. Both sources were consulted on 2026-10-09.

Choose Python with the already pinned pymavlink 2.4.50 decoder: only framing is
new; CRC, message semantics, signature verification and replay persistence stay
in the existing adapter. Generated C or Rust could reduce parsing overhead, but
would add a native boundary without evidence that these tiny bounded batches
need it. A generic streaming connection would add buffering/resynchronization
semantics and possible transmit surfaces that this interface does not require.

## Fixed v1 contract

- `DatagramTelemetryV1` exclusively owns a `PassiveTelemetry` or
  `SignedTelemetry` instance through public `ingest`, `snapshot`, `close` methods.
  Single owner/thread; do not access the underlying decoder concurrently.
- One bytes object contains 1–16 complete MAVLink 2 packets, at most 4480 bytes.
  Preflight the entire framing before decoding anything; no magic-byte scanning,
  partial-packet buffering, cross-datagram assembly or recovery past bad data.
- Only known signed/unsigned framing flags and zero compatibility flags pass.
  Each complete packet goes through the existing decoder, including its strict
  ATTITUDE/LOCAL_POSITION_NED allowlist. Heartbeats/commands are not skipped.
  Stop on the first UNKNOWN result; a valid tail must never hide rejection.
- Invalid framing clears observations through the decoder's public invalid-input
  path. Semantic/signature failure clears samples through the existing decoder.
  Already committed signing counters are never rolled back, including when a
  later packet in the same batch fails. This is not an atomic journal transaction.
- A separate monotonic datagram receipt deadline is 100 ms, including decode and
  journal time. All existing per-sample/authority deadlines also apply. The caller
  supplies the same trusted monotonic clock to both components when injecting a
  clock. Rollback/invalid clocks latch closed; silence expires samples. This
  bounds local processing age, not kernel/router queue or physical capture age.
  Each fully framed batch replaces the previous batch's samples before decoding;
  a new datagram cannot extend an earlier sample's receipt deadline. Sequence,
  source-clock and signing high-water marks survive that sample withdrawal.
- `UdpTelemetryV1` binds only IPv4 loopback, receives one bounded datagram per
  poll with a 20 ms socket timeout, and never transmits. The operator-owned router
  must already supply allowlisted messages. No auto-discovery, stream negotiation,
  rate request, TIMESYNC, heartbeat, ACK, command or actuation is added.
- Results remain `external_unverified`, capture time unknown, perception
  ineligible; signing only attests possession of the provisioned shared key.
  Only the existing two latest samples are retained; no trajectory/history.

Focused acceptance: real SDK-encoded synthetic wire batches; packet/count/byte
bounds; corrupt prefix/tail and no resynchronization; allowlist failure followed
by valid tail; signing/downgrade/replay; receipt expiry including decode time;
clock rollback; localhost UDP silence/oversize/no response; fixed-seed malformed
bytes. Existing single-packet and signing tests remain a regression baseline.
Full simulator matrices and hosted checks are separate pending evidence.

The focused `AETHRON passive robotics adapters` workflow runs synthetic wire
and loopback tests on Ubuntu 24.04 x86_64/CPython 3.13.15 with a Linux hash-locked SDK.
The Linux CPython 3.13 wheel hashes were retrieved on 2026-10-09 from official
PyPI metadata for [pymavlink](https://pypi.org/pypi/pymavlink/2.4.50/json),
[fastcrc](https://pypi.org/pypi/fastcrc/0.5.0/json), and
[lxml](https://pypi.org/pypi/lxml/6.1.3/json). The closure requires glibc>=2.28.
Workflow presence is not hosted execution evidence or simulator qualification.
