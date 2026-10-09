# Freshly verified synthetic rollout claims v1

## Requirements and technology decision (2026-10-10)

Before reserving the next wave, authenticate current source bytes and the pinned
key again; bind all immutable journal fields; reject expiry, rollback, stale
revisions and missing signed provisioning permission. A competing floor writer
must not advance between the final floor check and journal reservation.

Select Python context-managed composition of the bounded private snapshot and
SQLite writer transaction. A separate native service would introduce IPC and a
second lifecycle without solving the cross-file commit boundary. Combining both
records in one database would permit a single commit but requires a new storage
schema and migration; this revision instead makes partial failures explicit and
returns no claim unless both existing stores commit. No execution occurs within
the transaction, so unresolved reservations safely block progress for recovery.

Primary references: [SQLite transaction semantics](https://sqlite.org/lang_transaction.html)
and [Python context manager exception semantics](https://docs.python.org/3/library/contextlib.html).
`BEGIN IMMEDIATE` supplies writer serialization, while context exit commits or
propagates failure. No throughput, wall-clock latency or physical durability
qualification is inferred from those library contracts.

## API

`claim_rollout_wave(bundle, public_key, *, journal, floor_store, clock,
expected_revision, provisioning=False)` performs only synthetic/local bookkeeping:

1. Read the journal and floors. Sample trusted UTC at or above both committed
   times; copy the fixed four-file snapshot described by fleet-plan v1.
2. Verify the current signed policy and artifact. Require both content digests,
   version, capacity, batch size and validity window to match the journal. Even a
   newly signed policy with the same version cannot rebind an existing journal.
3. Require a strict boolean provisioning flag. If true, require the signed
   `allow_initial_provisioning` field. This selects reservation policy only; no
   device provisioning action or transferable permission is produced.
4. Resample trusted time, reject rollback/expiry and clean the temporary snapshot.
5. Enter `FleetFloorStore.guarded_advance`, which takes the floor writer lock,
   rereads both floors and prepares their update. A higher competing floor rejects
   this claim. Under that lock, resample time and reserve the journal wave using
   its expected revision, then sample time again to reject post-reservation expiry.
6. Commit floors when the guard exits. Return the slot tuple only after both
   commits complete successfully.

Lock order is floor writer, then journal writer. The floor database remains locked
through journal commit, so ordinary floor writers cannot pass the final check and
then supersede it before reservation. Same-plan journal mutation remains protected
by revision checks. The protected administrator directory assumption remains;
this is not protection from a malicious administrator replacing database files.

`guarded_advance` yields provisional `FleetFloors` for trusted local bookkeeping.
Never report success until context exit succeeds, and never perform external
execution inside it. Existing `advance` uses the same guard with no body, retaining
its commit-before-return semantics.

## Failure and authority limits

The stores still have separate commits. A journal reservation may commit before
floor commit fails, before the final time sample expires, or before process exit.
In these cases the gate returns no slots, the floor update rolls back, and the
running journal slots remain unresolved. They must not be erased or automatically
retried. A failed journal reservation rolls back the provisional floor update.
Tests preserve and inspect both outcomes; no cross-file atomicity claim is made.

Expected failures use `ValueError("invalid_fleet_claim")`. The caller owns trusted
time, the protected pinned-key path and store locations. No external callback,
installer, activation, transport, vehicle actuation or physical health assertion
exists in this API. The return is a bounded reservation, not lasting execution
authority: a real executor still needs its own operation capability, current trust
and time checks, and exact artifact bytes at use. I/O stalls after the final time
sample and later floor changes do not extend validity. Unfinished-reservation
recovery and authenticated remote receipts remain separate executable work.

## Focused verification

Tests use real ephemeral signatures and local SQLite. They cover successful
reservation, changed artifact/key, newer floors after verification, a competing
writer during reservation, final floor commit failure, expiry before/after
reservation, stale revisions, mismatched journal fields, same-version signed
policy replacement, and positive/negative signed provisioning permission.
