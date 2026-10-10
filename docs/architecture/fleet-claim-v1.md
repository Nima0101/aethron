# Freshly verified synthetic rollout claims v1

## Requirements and technology decision (2026-10-10)

Before reserving the next wave, authenticate current source bytes and the pinned
key again; bind all immutable journal fields; reject expiry, rollback, stale
revisions and missing signed provisioning permission. A competing floor writer
must not advance between the final floor check and journal reservation.

The [V3 review](fleet-claim-review-v3.md) retains a synchronous Python adapter
with native SQLite transactions after comparing Rust, C# and Erlang/Elixir
alternatives. Native implementations need not use IPC. A single database could
provide one commit, but would change the scope of the shared floor and per-plan
stores; this API instead exposes partial outcomes and never promises cross-file
atomicity. No runtime removes the need to check time after the last commit.
There is no throughput, real-time or physical durability qualification.

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
6. Commit floors when the guard exits. Then sample trusted time once more,
   requiring a strict bounded integer no earlier than the post-reservation sample
   and before exclusive expiry. Return slots only after this fifth sample passes.
   This sample is checked, not persisted; both stores retain their earlier times.

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

The stores have separate commits. A journal reservation can commit before a
pre-floor-commit time rejection or a floor commit failure; the uncommitted floor
update rolls back while running journal slots remain. If the new final time
check rejects **after floor commit**, both committed stores remain. A missing
response or an error is not proof of rollback: inspect both stores and never
clear reservations or lower floors to make a retry succeed. A failed journal
reservation before its commit rolls back the provisional floor update. No
cross-file atomicity or external exactly-once execution is claimed.

Expected failures use `ValueError("invalid_fleet_claim")`. The caller owns trusted
time, the protected pinned-key path and store locations. No execution callback,
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

The V3 correction adds the post-floor-commit sample. Three retained failing tests
showed previously accepted late expiry, accepted clock exhaustion and a missing
fifth observation. Fifteen claim tests now pass, with 49 focused claim/plan/floor
tests in total. See [evidence](../verification/fleet-claim-review-v3.json). The
changed-key test checks caller-selected trust, not a built-in revocation service.
No MLS/CNSA, five-nines or tactical deployment qualification is established.
Insufficient information for tactical deployment.
