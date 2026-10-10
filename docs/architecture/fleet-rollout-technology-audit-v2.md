# Rollout journal technology audit v2

Audit policy version: **2**. Decision: **KEEP SQLite's native transaction engine
with the synchronous Python state adapter; require verified DELETE/EXTRA
durability settings.** Component introduced in `4934d67`, reviewed through
`19e36c427a2b3be3fb4912f6129977b5e8196ff9`. This supersedes the original technology
rationale and FULL-mode recommendation in `fleet-rollout-v1.md`. It is the fifth
of eight chronological component decisions, not lane audit completion.

## Operational constraints

One protected local Linux file stores one immutable content-pinned plan, a
revision, committed time and at most 1024 anonymous slot states. Competing
processes must serialize compare-and-update; a reservation or result must survive
reopening after success. Only one wave of at most 32 slots may run. Terminal
failure is sticky, lost responses never release reservations, and reopening must
not reset missing, corrupt or incompatible state. The database admission cap is
1 MiB, the strict JSON record cap 16 KiB, and the writer busy timeout 100 ms.
Neither that timeout nor caller-supplied time bounds filesystem/scheduler delay.
No deployment transport, distributed scheduler, replication, append-only history,
actuator operation or hard realtime guarantee belongs in this journal.

The relevant choice includes engine, binding and state representation. Native
transaction durability is separate from validating legal state transitions.
Retaining either layer requires evidence, not an assumption based on its language.

## Candidate comparison

Primary sources consulted 2026-10-10. Judgments are specific to these constraints;
no language throughput ranking or platform qualification is inferred.

| Candidate | Evidence and assessment |
| --- | --- |
| SQLite C engine, Python adapter, bounded whole-record JSON | SQLite documents its rollback-journal recovery and commit protocol. [Atomic commit](https://sqlite.org/atomiccommit.html). One writer transaction covers pins, state vector, revision and time together. Whole-record validation keeps cross-slot invariants in one bounded function and uses parameterized SQL. No service or application-owned crash log is needed. Python does not supply native durability; SQLite does. |
| SQLite through Rust or C# with typed state | [.NET transactions](https://learn.microsoft.com/en-us/dotnet/standard/data/sqlite/transactions) expose the same serialized engine. Typed enums can reduce programming mistakes, but stored bytes, global wave ordering, stale revision and commit outcomes still need validation. These are credible in-process alternatives, not necessarily separate executables. For this local API there is no demonstrated missing capability or bottleneck offsetting an additional cross-runtime interface; schema interoperability remains available for a future different host. |
| Normalized SQL tables/constraints or SQLite JSON functions | [SQLite JSON functions](https://www.sqlite.org/json1.html) allow native inspection of JSON. Per-slot rows permit selective updates, but wave/revision invariants span rows and require transactional aggregate checks or triggers. A 1024-slot vector is bounded and the current schema admits no triggers. Normalization is a credible scale option, not a material improvement for this capped record without measured update pressure. SQL JSON parsing alone does not prove the closed-schema state machine. |
| LMDB native key/value engine with language bindings | [LMDB binding documentation](https://lmdb.readthedocs.io/en/release/) describes one writer, transactional memory mapping and sync controls. One atomic value fits naturally. It still needs the entire application state validator and explicit durability configuration. No missing read concurrency or key lookup capability justifies switching engines for this one-record journal. |
| Rust redb or Go bbolt | [redb durability](https://docs.rs/redb/latest/redb/enum.Durability.html) distinguishes immediate persistence from unsynchronized commits; [bbolt](https://pkg.go.dev/go.etcd.io/bbolt) documents embedded transactions and synchronization options. Both are credible embedded engines. Neither removes failure/revision validation or the need to verify process-sharing and recovery semantics for this API. Static typing is useful but does not fix a weaker durability setting. |
| Erlang/Elixir Mnesia | [Mnesia](https://www.erlang.org/doc/apps/mnesia/mnesia.html#sync_transaction/3) provides synchronous transactions with disk logging when disk tables are used. Supervision/replication would be valuable in a distributed scheduler. They add configuration and recovery state here without a distribution requirement; automatic transaction retries must not become repeated external execution. |

KEEP selects native atomic persistence plus a bounded synchronous validator with
no additional scheduling or message protocol. It does not rely on installed
tooling, familiarity or rewrite expense. Stronger typing is a real alternative
benefit; the independent transition comparison below directly checks the global
invariant that types alone cannot establish. There is no evidenced requirement
advantage requiring a language or database-format migration in this component.
The correction is the engine durability profile, which applies regardless of
wrapper language. There is no claim that an unimplemented contender was benchmarked.

## Correction and executable evidence

SQLite documents an additional directory synchronization step for EXTRA in DELETE
mode; FULL can lose the last committed transaction after power loss on some
filesystems. [Synchronization modes](https://sqlite.org/pragma.html#pragma_synchronous).
The journal now checks the returned journal mode, requests EXTRA, and reads back
the synchronous value 3 before exposing any connection. A weaker setting rejects
with the existing fixed error before a state mutation. This covers initialization,
snapshots, reservations and result recording without changing storage schema.

Before implementation, an instrumented real connection observed `delete, 2` at
all three commits: creation, claim and failure receipt. Separate connections
injected OFF synchronization and MEMORY journaling; both allowed reservation
success. These three failing assertions are preserved in the evidence record.
After correction, the expected profile is observed and both weaker settings
reject while preserving the original snapshot.

Four bounded child processes exit immediately before or after the actual SQLite
COMMIT for a claim or a failed result. Before COMMIT, reopening recovers the whole
old snapshot. After COMMIT but before the caller receives a response, reopening
retains the reserved wave or failure receipt and increased revision; another
claim is rejected. This exercises process death and response ambiguity, with
the OS still running. It is not a physical power-loss experiment.

A separate executable reference explores legal claim/result transitions from
four pending slots for batch sizes 1 through 4. It compares reachability against
the production validator over all 4^4 state vectors and revisions 0 through 8:
**9216 comparisons**. The reference generates transitions rather than repeating
the validator's count formula. All agree. This is a bounded conformance check,
not a proof for all 1024 slots; existing maximum-capacity and contention tests
remain active. No large fuzz run or storage throughput benchmark was performed.

See [audit evidence](../verification/fleet-rollout-technology-audit-v2.json) for
source hashes, exact focused commands and retained failures. An initial unused
test-variable lint finding was corrected without suppression.

## Assurance limits

EXTRA relies on the OS, filesystem and device honoring synchronization. No test
qualifies power loss or prevents an administrator from restoring an old backup.
The protected directory assumption excludes concurrent malicious path replacement
and NFS. The journal does not authenticate callers or receipts; signed plan and
claim adapters provide separate boundaries and remain next in the audit.
Persistent reservations are bookkeeping, not execution authority. State is
historical after expiry, and no failure or unresolved reservation is automatically
cleared. There is no cross-database atomicity or exactly-once external execution
claim. The unchanged fixed bounds have not been weakened to obtain a passing test.
