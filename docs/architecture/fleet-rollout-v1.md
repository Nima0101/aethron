# Bounded local rollout journal v1

## Technology decision (2026-10-10)

Requirements: one immutable plan, up to 1024 anonymous slots, restart persistence,
serialized competing writers, atomic reservation/result updates, bounded state,
no network/service dependency and no installer or hardware assumptions.

[SQLite transactions](https://sqlite.org/lang_transaction.html) supply a local
writer transaction and explicit commit. [Rust redb](https://docs.rs/redb/latest/redb/)
offers embedded transactional storage; [Go bbolt](https://pkg.go.dev/go.etcd.io/bbolt)
is another embedded transactional option. Select SQLite through Python's standard
binding for this bounded SQL record: the alternative bindings would add a new
executable or extension distribution without improving the required single-writer
semantics. This is a requirements-based choice, not a hardware benchmark result.
No database server, message broker, remote job service or platform updater is needed.

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
slot indices are local ordinals, never durable device or person identities.

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
reopen. SQLite uses DELETE journaling, FULL synchronous mode, a 100ms busy timeout,
a 1MiB database admission bound and a 16KiB JSON record bound. The timeout is not a
wall-clock deadline under host scheduling or filesystem stalls. Transactions
close without commit on rejection; injected commit failure preserves old state.
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
and an injected failed COMMIT. The signed-policy workflow runs the journal tests
against installed wheels. Authentication-to-journal binding and recovery remain
separate executable work; they are not inferred from these primitive tests.
