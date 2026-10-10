# Fleet committed floors v1

P3.4 policy admission needs durable lower bounds for version and trusted UTC.
This component stores one pair of committed floors, not identities, health
history or a deployment authorization. The local administrator controls the
database and its directory; physical rollback of a database backup is outside
this software boundary. P11 cannot expose raw floor writes to remote clients.

## Technology decision (2026-10-10)

Requirements: atomic paired updates, serialization across local writers, bounded
lock contention, no service/network dependency, low storage/memory overhead and
restart persistence. The [fresh V3 review](fleet-floors-review-v3.md) retains
SQLite's native transaction engine through the Python binding after comparing
embedded transactional stores, managed/native bindings and fixed-file protocols.
A native binding need not introduce a service. Selection rests on the complete
transaction/recovery boundary, not installed tools or rewrite cost.

Primary sources: [SQLite transactions](https://sqlite.org/lang_transaction.html),
[atomic commits and assumptions](https://sqlite.org/atomiccommit.html),
[synchronous modes](https://sqlite.org/pragma.html#pragma_synchronous).
Use `BEGIN IMMEDIATE`, verified DELETE journaling and verified EXTRA synchronous
mode (numeric value 3). The implementation rejects weaker/unavailable modes.
EXTRA includes journal-directory synchronization after unlink. No WAL,
external database, schema migration, extension loading or network is introduced.
The API rejects lock contention after SQLite's 100ms busy timeout; this is not
a wall-clock latency guarantee under host scheduling or filesystem stalls.

## Contract

`FleetFloorStore.initialize(path, minimum_version, minimum_time_s)` exclusively
creates a mode-0600 database and commits exactly one versioned row. It never
overwrites an existing file. Interruption before commit can leave an unusable
file for explicit administrator recovery. Interruption after commit can leave
the committed row even though no result reached the caller. Neither case permits
automatic deletion, reinitialization or resetting of floors.

`FleetFloorStore(path).read()` requires an existing regular database of at most
1MiB and returns immutable `FleetFloors(minimum_version, minimum_time_s)`.
Unknown schema, extra tables/triggers/views, missing rows, invalid values,
corruption, missing files, links and special files fail closed. Reopening never
initializes. The directory must be protected against concurrent path replacement;
the library does not claim to sandbox a hostile filesystem administrator.

`advance(minimum_version, minimum_time_s)` atomically checks and replaces the
pair. Neither committed value may decrease. Version is a strict integer in
1..2^31-1; time is a strict integer in 0..2^53-1. Equal values are idempotent.
No success result is returned until COMMIT succeeds. Rejected input or an aborted
uncommitted transaction leaves the previous pair. Absence of a success result
does not prove rollback: a process may stop after COMMIT but before returning.
On an uncertain outcome, reopen and validate the store without lowering either
floor; never recreate it using a cached pair. A fresh instance rereads the
database, never a cached floor. Handled storage/input failures use
`ValueError("invalid_fleet_floor")`; process termination is not an API error.

`guarded_advance(...)` holds the writer transaction around local bookkeeping.
The yielded value is provisional until normal context exit commits. An exception
inside the context aborts the uncommitted transaction. External execution is
forbidden inside this guard; it cannot make another store or device atomic with
this one.

These are **committed floors**, not a record of every attempted input or a
trusted-clock source. The caller must authenticate policy before advancing a
version, retain trustworthy UTC, and commit the relevant floor before permitting
an operation that depends on it. A future policy/executor adapter must coordinate
admission and execution; calling `read()` and later acting on its result alone
is not an atomic authorization. This store does not prove key trust, bundle
compatibility, safe activation, hardware durability or protection from restoring
an old database file. There is no factory-reset API.

## Focused verification

Eighteen tests cover reopening, regressions, competing instances, failed commit,
locked database, missing/corrupt/link/special/oversized files, strict scalar
bounds and verified durability settings. Bounded child-process exits cover
before commit, after a successful call and after COMMIT before the call returns.
The last case retains the complete new pair and rejects a subsequent regression.
These tests leave the operating system running; they do not simulate loss of
power or qualify a storage controller/filesystem combination.

The 1 MiB database-file admission limit is not a total process-memory or temporary
file quota. There is no replication, cryptographic rollback anchor, encryption,
MLS isolation, real-time scheduling or uptime guarantee. Trusted storage must
honor SQLite's synchronization assumptions. Insufficient information for tactical
deployment.
