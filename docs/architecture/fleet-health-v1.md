# Fleet health v1 — bounded software health projection

This additive P3.4 interface does not change frozen perception or update contracts.
It reports runtime availability, never scene safety, hardware qualification,
location, imagery, tracks, people, credentials or OEM compatibility.

## Technology decision

Requirements: fixed resource bounds, fail-closed freshness, closed public fields,
no network or persistence, and reuse by the existing local appliance supervisor.
Choose a Python standard-library module with immutable report records and a fixed
slot table. Python supports this small control-plane operation without another
runtime or dependency. A Go collector would add a process and protocol before
there is a network requirement; a general OpenTelemetry collector would add a
configuration and export surface unnecessary for five counters. This choice is
based on the boundary requirements, not an implementation-language constraint.

Primary research consulted 2026-10-09:
- [OpenTelemetry sensitive data guidance](https://opentelemetry.io/docs/security/handling-sensitive-data/)
  motivates collecting only necessary attributes at the producer.
- [Prometheus metric naming guidance](https://prometheus.io/docs/practices/naming/)
  warns against identifiers and other unbounded label dimensions.

## Contract

`encode_local_health(status, now_ms)` projects a local supervisor status dictionary
into JSON bytes containing exactly `version`, `state`, `emitted_ms` and
`status_expires_ms`. Other supervisor fields are never serialized. Version is
integer 1; state is running/recovering/fault/stopped. Timestamps are strict
integers in 0..2^53-1, emitted <= now < expires, and lifetime is 1..2000ms,
matching the existing supervisor status lifetime. Projection fails with a fixed
error for malformed or stale selected fields. Input must come from the local
supervisor, not arbitrary remote telemetry.

`FleetHealth(slot_count)` allocates 1..1024 slots once. Caller-owned authorization
maps each appliance to one integer slot; neither authorization nor that mapping
is exported. `ingest(slot, raw, now_ms)` accepts at most 256 bytes of strict UTF-8
JSON with exactly the four fields above. It rejects duplicates, unknown fields,
nonfinite numbers, boolean numbers, invalid states and timestamps. A rejected
report clears that slot and returns false. Accepted emitted timestamps must
strictly increase per slot; the high-water timestamp survives rejection/expiry.
Only one current immutable report plus one timestamp is retained per slot.

`snapshot(now_ms)` returns version, total, five state counts (including unknown),
`scene_state: UNKNOWN` and `qualified: false`. Expired/missing slots are unknown.
Repeated snapshots never extend a report lifetime. Collector clock regression or
invalid time clears all reports and raises a fixed error, retaining clock and
per-slot high-water marks. Invalid slot arguments clear reports and raise a fixed
error. No callbacks, I/O, logs, free-text diagnostics, IDs or history are emitted.
Calls are serialized by a lock. A new collector starts entirely unknown.

All timestamps must already share one trusted local monotonic clock domain.
Never compare remote boot clocks directly or refresh stale data on receipt.
Cross-host authentication, clock mapping, replay protection across collector
restarts, slot provisioning and collection transport are **not implemented** by
this interface. Local callers are trusted to supply the clock and slot mapping.
This library does not send reports, activate updates or actuate vehicles.

## Implementation and verification plan

1. Add focused failing tests for projection privacy, counts, expiry boundaries,
   replay after expiry/rejection, clock rollback, invalid schemas and bounds.
2. Implement `runtime/fleet_health.py`; keep the supervisor and P3.1 internals
   unchanged. The exported helper consumes `ApplianceSupervisor.status()`.
3. Run focused unittest, formatting/lint and deterministic adversarial inputs.
   Add the installed test to the existing edge-contract CI job.
4. Record results and limitations. Commit and deliver through the lane branch
   when Git metadata access permits. Full matrix, packaging/clone reproduction
   and broad fuzz belong to hosted verification, per the lane execution policy.
