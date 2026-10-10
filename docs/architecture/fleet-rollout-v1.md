# Bounded local rollout journal v1

The [fresh V3 review](fleet-rollout-review-v3.md) confirms the current SQLite /
bounded Python implementation and corrects durability, recovery and privacy
wording. The [V2 audit](fleet-rollout-technology-audit-v2.md) remains historical
evidence, including the failing durability tests. The schema and bounds are
unchanged. Connections require verified DELETE journaling and EXTRA synchronization.

## Technology decision

One immutable plan needs bounded state, restart persistence and atomic
reservation/result updates across local writers. No network service, installer,
hardware identity or distributed scheduler is required. The V3 assessment
compares native SQLite bindings in Python, Rust and C#, normalized SQL, Rust redb
and Erlang/Elixir Mnesia. It retains the native transaction engine plus a
synchronous whole-record validator. Other bindings need not introduce IPC, and
neither installed tooling nor rewrite expense is a selection criterion. No
comparative speed, real-time or hardware qualification is claimed.

## Contract

`RolloutJournal.initialize(path, *, policy_sha256, artifact_sha256, version,
slot_count, batch_size, not_before_unix_s, expires_unix_s, now_unix_s)` exclusively
creates a mode-0600 journal. The caller must authenticate the policy and exact
artifact and bind every plan field before creation. Hash strings are explicit
pins, **not proof of authentication or that bytes were installed**. This primitive
has no public network endpoint and must not receive unauthenticated receipts.

A plan has lower-case 64-character SHA-256 pins, version 1..2^31-1, 1..1024 slots,
batch size 1..min(32, slots), and an exclusive validity window of at most 86400
seconds. Times are strict integers in 0..2^53-1. Each journal represents one plan;
slot indices are local ordinals, not device or person identity fields. This does
not guarantee anonymity: a caller-held mapping can associate a slot with a device.
Protect the journal and avoid exporting such mappings or per-slot results.

`claim(expected_revision, now_unix_s)` commits the next ascending wave of pending
slots and returns its ordinals. Only one wave may be running. No new claims are
allowed after any recorded failure or when all slots have succeeded. Reopening
preserves running slots; it never retries, releases or pretends to finish them.

`record(slot, outcome, policy_sha256, artifact_sha256, expected_revision,
now_unix_s)` accepts only a running slot, matching content pins and a terminal
`succeeded` or `failed` outcome. These are caller-reported software workflow
results, not physical health or qualification. Terminal outcomes cannot be
rewritten. Other running slots can settle after a failure, preserving the failure.

Both operations compare revision and monotonic committed time under `BEGIN
IMMEDIATE`. They reject stale revisions, time rollback and expiry, then validate
and commit the entire updated state before returning. A duplicate request is
rejected by its revision; callers may inspect the snapshot to reconcile a lost
response. There is no exactly-once external execution guarantee.

`snapshot()` reads a consistent immutable record, including after expiry so
negative evidence remains available. A snapshot is historical bookkeeping and
cannot authorize a new operation. Revision is bounded by 2048; the only legal
progress is pending -> running -> succeeded/failed. Closed-schema validation
also checks contiguous wave allocation, terminal predecessor waves and revision
consistency. No timestamps or per-slot histories are accumulated.

## Storage and assurance boundary

The administrator supplies a protected local directory, never NFS. Existing files
are never overwritten; missing/corrupt/link/special files are not initialized on
reopen. SQLite verifies DELETE journaling and EXTRA synchronous mode on every connection,
with a 100ms busy timeout,
a 1MiB database admission bound and a 16KiB JSON record bound. The timeout is not a
wall-clock deadline under host scheduling or filesystem stalls. Transactions
close without commit on pre-commit rejection. A failure injected before the real
COMMIT preserves old state; an exception after the real COMMIT preserves the new
state. An error or absent response is not proof of rollback. Reopen and inspect
state; never reset the journal or repeat external work based on a missing response.
These file/record caps are not a process-memory or temporary-file quota.
Expected input/storage errors use `ValueError("invalid_fleet_rollout")`.

There is no automatic reset, cleanup, retry, cancellation or failure override.
An unfinished/expired journal remains for explicit recovery design. Stalls after
the caller's time sample may outlast validity. An executor must independently
recheck time, trust, committed floors, exact content and operation capability.
Claims reserve bookkeeping slots only; this module performs no installation,
activation, networking or vehicle actuation. The protected journal is not tamper-
proof against an administrator or an old backup restore. Power-loss behavior,
physical platform compatibility and real deployment qualification are unclaimed.

## Focused verification

Synthetic transitions cover successive bounded waves, restart persistence, sticky
failure, stale writers, both content pins, strict inputs, expiry/time rollback,
foreign schemas, missing/corrupt/link state, maximum capacity, real lock contention
and errors before/after COMMIT. Fifteen journal tests pass, including four
process-death cases and 9216 bounded state/revision comparisons. The signed-policy
workflow includes installed-wheel journal tests; this review ran focused source
tests only. Signed plan and claim adapters exist as separate components and remain
subject to their own V3 review. No receipt authentication or automated recovery
is inferred from these primitive tests. No MLS/CNSA, five-nines or physical
durability qualification is established. Insufficient information for tactical
deployment.
