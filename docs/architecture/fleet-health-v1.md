# Fleet health v1 — bounded software health projection

This additive P3.4 interface does not change frozen perception or update contracts.
It counts fresh caller-reported software states, never verified availability,
scene safety, hardware qualification,
location, imagery, tracks, people, credentials or OEM compatibility.

## Technology decision

The [fresh V3 review](fleet-health-review-v3.md) retains the bounded local Python
library after checking parser semantics, fixed state and synchronous call
requirements against native and managed alternatives. Other languages can use
in-process bindings; they do not inherently require a separate service. Existing
tooling or rewrite effort is not a reason for this choice. Neither the 2000 ms
validity rule nor synthetic measurements establish a processing deadline.

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

These counts do not verify the reporter's claims or probe an appliance. Removing
identifiers is data minimization, not anonymity: with one slot, its state is
visible, and changes between snapshots may reveal individual transitions. Treat
counts as operational information and control access at the caller boundary.
The returned dictionary is a detached observation at the supplied time, with no
embedded observation time or expiry. A saved dictionary does not update or expire
itself; callers must request a fresh snapshot for a later observation. It is not
a portable freshness token or an authorization decision.

All timestamps must already share one trusted local monotonic clock domain.
Never compare remote boot clocks directly or refresh stale data on receipt.
Cross-host authentication, clock mapping, replay protection across collector
restarts, slot provisioning and collection transport are **not implemented** by
this interface. Local callers are trusted to supply the clock and slot mapping.
This library does not send reports, activate updates or actuate vehicles.

## Implementation and verification status

The local collector and supervisor projection are implemented. Fifteen focused
tests cover field exclusion, counts, exclusive expiry, replay after rejection,
clock rollback, malformed schemas and bounded hostile byte inputs. The existing
edge-contract CI job includes the health tests. The V3 review records a fresh
run and a 22-case strict-decoder comparison; it does not certify this lane's
other components or replace hosted packaging, reproduction or broader checks.

This component provides no cryptography, MLS separation, cross-domain guard,
Link 16/DDS transport, hard real-time scheduling or availability SLA. Those
properties cannot be inferred from enum validation or aggregate counts. No
tactical deployment qualification is established: insufficient information for
tactical deployment.
