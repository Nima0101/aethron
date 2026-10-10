# Fleet admission with committed floors v1

This is the current return contract. The historical
[technology audit v2](fleet-admission-technology-audit-v2.md) retains evidence of
the corrected pre-commit-only check. The [fresh V3 review](fleet-admission-review-v3.md)
rechecks the implementation, technology choice and failure semantics. The API and
frozen numeric limits are unchanged.

## API and ordering

`admit_fleet_policy(bundle, public_key, *, floor_store, clock)`:

1. Read the existing protected `FleetFloorStore`; never initialize missing state.
2. Sample caller-owned trusted UTC seconds. Require a strict integer in
   `0..2**53-1` at or above the committed time floor.
3. Authenticate and validate with `load_fleet_policy`, using the persisted
   version floor and first time sample. No unverified version is persisted.
4. Resample trusted UTC after verification. Require a bounded integer no earlier
   than the first sample and inside the policy's exclusive expiry window.
5. Atomically advance version and time through the store. Its writer transaction
   rereads both floors; a competing advance past either candidate rejects this
   admission. The persisted time is the second sample.
6. After successful commit, sample trusted UTC again. Require a bounded integer
   no earlier than the second sample and inside the validity window. Return the
   immutable configuration only after this check succeeds.

A rejection before this caller commits does not advance its floors. A rejection
at the final clock check **preserves the committed pair**. A missing success
acknowledgment does not prove rollback; reopen the store and never reset floors
as recovery. Another writer can independently advance them. The last time sample
is checked but not persisted: persisting it would introduce another commit that
could itself delay the return.

Handled `OSError`, `ValueError`, `TypeError`, `RuntimeError` and `StopIteration`
use `ValueError("invalid_fleet_admission")`, without provider error details or
automatic retry. This is not a promise to catch every exception from arbitrary
extension code. The callable and store are trusted local code. The pinned key,
trustworthy time source and administrator-controlled local database directory
remain caller responsibilities.

## Technology and deployment limits

The synchronous Python adapter composes native OpenSSL verification and SQLite
writer transactions. Rust/native bindings, C#/.NET, Node and BEAM alternatives
are viable candidates; they do not inherently require IPC. The
[V3 comparison](fleet-admission-review-v3.md) explains why this small local
composition has no evidenced material migration winner under its current
requirements. There is no new service, wire format or retry protocol.

The result is configuration admitted at the last sampled instant, **not lasting
execution authority**. Filesystem or scheduling stalls can delay return. Another
admission can supersede it after commit, including before the final sample.
Consumers must recheck trust, current time, floors and exact content at their own
operation boundary. This API neither activates software nor reserves a slot.

The store records committed floors, not every attempted observation of time.
Versions are lower bounds, not a persistent digest registry: two correctly
signed policies at the same version are not distinguished by this store. The
separate rollout journal binds exact content; this admission API does not make
transactions across stores atomic. The
[loader limits](fleet-policy-v1.md) and [storage assumptions](fleet-floors-v1.md)
apply. No end-to-end deadline, memory qualification, distributed consistency,
CNSA/MLS compliance or five-nines availability is established. Restored old
backups, a compromised trusted key/clock and storage hardware behavior remain
outside this component's assurance. Insufficient information for tactical deployment.

## Focused verification

Sixteen tests use ephemeral Ed25519 signatures and local SQLite to exercise
commit-before-return, restart rollback rejection, invalid signatures, malformed
or backward time, expiry, competing advances, missing state and commit failure.
Nine new clock-provider error subcases verify fixed errors, no retry and reopened
floor values before and after commit. See the
[source-bound evidence](../verification/fleet-admission-review-v3.json).
No network, installation, actuation or physical qualification is tested or claimed.
