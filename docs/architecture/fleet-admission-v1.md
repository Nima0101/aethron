# Fleet admission with committed floors v1

The [technology audit v2](fleet-admission-technology-audit-v2.md) amends the
return boundary: admission also checks trusted time **after** the floor commit.
A rejection at that final check preserves committed floors. The original
pre-commit-only behavior described below remains historical evidence, not the
current return contract. The API and frozen numeric limits are unchanged.

## Requirements and technology decision (2026-10-10)

The local fleet boundary must authenticate bounded policy bytes, reject version
or trusted-time rollback across restarts and competing admissions, and never
return a configuration if its floor commit fails. No deployment, remote service,
identity history or actuator operation belongs in this boundary.

Select an in-process Python adapter over OpenSSL signature verification and
SQLite's serialized writer transaction. The requirement is composition of two
small local contracts, with no new wire format or service lifecycle. A standalone
Go/Rust verifier plus database binding would require an additional executable and
cross-process result binding without removing the need for transactional floor
checks. A database service is unnecessary for one protected local record. This
choice makes no latency or memory qualification claim.

Primary references: [TUF client workflow](https://theupdateframework.github.io/specification/latest/)
for authenticated metadata, expiry and rollback checks; [SQLite transactions](https://sqlite.org/lang_transaction.html)
for writer serialization; [Python SQLite API](https://docs.python.org/3/library/sqlite3.html)
for the local binding. This narrow contract does not implement or claim TUF
conformance, key rotation, threshold signatures or repository metadata roles.

## API and ordering

`admit_fleet_policy(bundle, public_key, *, floor_store, clock)`:

1. Read the existing protected `FleetFloorStore`; never initialize missing state.
2. Sample caller-owned trusted UTC seconds. Require a strict bounded integer at
   or above the committed time floor.
3. Authenticate and validate with `load_fleet_policy`, using the persisted
   version floor and first time sample. No unverified version is persisted.
4. Resample trusted UTC after signature verification. Reject backward time,
   malformed time and policy expiry at the exclusive end of its validity window.
5. Atomically advance the pair through the store. Its writer transaction rereads
   both floors; a competing advance past either candidate value rejects this
   admission. Return immutable configuration only after a successful commit.

A rejected admission leaves this caller's floors unchanged; a concurrent writer
may independently advance them. Expected input, clock and storage errors use
`ValueError("invalid_fleet_admission")`. The callable and store are trusted local
code, not remote extension points. The pinned key, trustworthy time source and
administrator-controlled local database directory remain caller responsibilities.

## Limits and next boundary

The result is configuration admitted at the last sampled instant, **not lasting
execution authority**. Filesystem stalls can delay commit or return. Another
admission can supersede it immediately after commit. An executor must recheck
trust, current time, floors and exact content at its own operation boundary;
this API neither activates software nor reserves an execution slot.

The store records committed floors, not every attempted observation of time.
Versions are lower bounds, not a persistent digest registry: two correctly
signed policies at the same version are not distinguished by this store. A
future rollout journal must bind the exact artifact and policy content, handle
idempotency and preserve failure evidence. Restoring an old database backup,
compromising the trusted key/clock, filesystem power-loss behavior and hardware
qualification remain outside this component's assurance.

## Focused verification plan

Real ephemeral Ed25519 signatures and local SQLite exercise commit-before-return,
restart rollback rejection, invalid signatures, clock rollback and malformed
samples, expiry during verification, concurrent version/time advances, missing
state and injected commit failure. No network or deployment operation is tested
or claimed. Add the adapter tests to the installed fleet-policy workflow.
