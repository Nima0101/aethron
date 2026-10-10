# Fleet committed floors v1

P3.4 policy admission needs durable lower bounds for version and trusted UTC.
This component stores one pair of committed floors, not identities, health
history or a deployment authorization. The local administrator controls the
database and its directory; physical rollback of a database backup is outside
this software boundary. P11 cannot expose raw floor writes to remote clients.

## Technology decision (2026-10-10)

Requirements: atomic paired updates, serialization across local writers, bounded
lock contention, no service/network dependency, low storage/memory overhead and
restart persistence. A handwritten JSON replacement plus locks would require
independent transaction/recovery machinery; a server database introduces an
operational dependency for a single row. Select SQLite's C transaction engine
through the standard Python binding. Native bindings in Go/Rust are credible
for a future standalone service but do not improve this single-row transaction
contract sufficiently to justify a new binary distribution here.

Primary sources: [SQLite transactions](https://sqlite.org/lang_transaction.html),
[atomic commits and assumptions](https://sqlite.org/atomiccommit.html),
[synchronous modes](https://sqlite.org/pragma.html#pragma_synchronous).
Use `BEGIN IMMEDIATE`, DELETE journaling and FULL synchronous mode. No WAL,
external database, schema migration, extension loading or network is introduced.
The API rejects lock contention after SQLite's 100ms busy timeout; this is not
a wall-clock latency guarantee under host scheduling or filesystem stalls.

## Contract

`FleetFloorStore.initialize(path, minimum_version, minimum_time_s)` exclusively
creates a mode-0600 database and commits exactly one versioned row. It never
overwrites an existing file. A failed initialization leaves an unusable file
for explicit administrator recovery; it never silently resets state.

`FleetFloorStore(path).read()` requires an existing regular database of at most
1MiB and returns immutable `FleetFloors(minimum_version, minimum_time_s)`.
Unknown schema, extra tables/triggers/views, missing rows, invalid values,
corruption, missing files, links and special files fail closed. Reopening never
initializes. The directory must be protected against concurrent path replacement;
the library does not claim to sandbox a hostile filesystem administrator.

`advance(minimum_version, minimum_time_s)` atomically checks and replaces the
pair. Neither committed value may decrease. Version is a strict integer in
1..2^31-1; time is a strict integer in 0..2^53-1. Equal values are idempotent.
No success result is returned until COMMIT succeeds. Rejected input or a failed
transaction leaves the previous pair; a fresh instance rereads the database,
never a cached floor. Every failure uses `ValueError("invalid_fleet_floor")`.

These are **committed floors**, not a record of every attempted input or a
trusted-clock source. The caller must authenticate policy before advancing a
version, retain trustworthy UTC, and commit the relevant floor before permitting
an operation that depends on it. A future policy/executor adapter must coordinate
admission and execution; calling `read()` and later acting on its result alone
is not an atomic authorization. This store does not prove key trust, bundle
compatibility, safe activation, hardware durability or protection from restoring
an old database file. There is no factory-reset API.

## Focused plan

Test first: reopening, regressions, competing instances, failed commit, locked
database, missing/corrupt/link/special/oversized files and strict scalar bounds.
Implement the store; run focused unit/lint/security checks and add the tests to
the existing Linux fleet workflow. Hardware crash/power tests remain external.
