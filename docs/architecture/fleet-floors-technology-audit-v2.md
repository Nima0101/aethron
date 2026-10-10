# Persistent fleet floors: technology audit v2

Audit policy version: **2**. Decision: **KEEP SQLite's native transaction engine
with its Python standard binding; replace FULL with verified EXTRA synchronization
for DELETE journaling.** This reviews the store introduced in `74606ae` through
`7c9107528ad18fb0a201548f0deb3686197582d0`, including its guarded writer transaction.
It supersedes the FULL-mode recommendation in `fleet-floors-v1.md`. The exact row
schema, public API, numeric bounds and busy timeout remain unchanged. No database
rewrite or language migration is required. This does not complete the lane audit.

## Requirements established first

The store persists one version/time pair in a protected local Linux directory.
Independent local writers must reread and reject regressions under the same lock;
the pair must be committed atomically before success is returned. It must reopen
without defaults, reject missing/corrupt/unexpected schemas, and retain the old
pair after a failed transaction. Capacity remains 1 MiB and lock contention uses
the existing 100 ms busy timeout. That timeout does not bound filesystem stalls
or host scheduling. The guarded transaction may surround local bookkeeping but
never external execution. There is no remote database, replication, query-volume,
realtime, appliance-RAM or hardware qualification requirement.

The relevant technology is the **storage engine plus binding and commit policy**,
not just the language wrapping two integers. Durability relies on the OS,
filesystem and device honoring synchronization. Restoring an old database copy,
malicious same-user path replacement and NFS remain outside the contract.

## Evidence-backed alternatives

Primary sources consulted 2026-10-10. Assessments are engineering judgments under
the requirements above, not measured throughput rankings.

| Candidate | Relevant primary evidence | Assessment |
| --- | --- | --- |
| SQLite C engine through Python, Rust or C# bindings | SQLite provides journaled atomic commit; Microsoft.Data.Sqlite also exposes transactions over this engine. [SQLite commit protocol](https://sqlite.org/atomiccommit.html), [.NET transactions](https://learn.microsoft.com/en-us/dotnet/standard/data/sqlite/transactions) | Native cross-process serialization and recovery already satisfy the needed storage operations. Changing only the wrapper language does not repair commit-mode selection. The Python binding keeps input checks and immutable results small while all transactional persistence remains native. C# and Rust bindings remain credible if a different hosting API is required. |
| LMDB C engine with language bindings | Its maintained Python binding documents transactional memory mapping, one writer and sync/metasync options. [LMDB binding documentation](https://lmdb.readthedocs.io/en/release/) | Credible low-overhead transactional alternative. Virtual map size is not equivalent to resident RAM. Would require a bounded binary record/schema contract and reviewed sync/locking settings; no missing query or concurrency capability makes that a material improvement for one pair. |
| Rust redb | `Durability::Immediate` persists commits, while `None` does not provide that guarantee. [redb durability](https://docs.rs/redb/latest/redb/enum.Durability.html) | Credible safe native embedded database. It still needs explicit durability selection, adapter/error behavior and process-sharing validation for this API. No benchmark or claim of inferior speed is made. |
| Go bbolt | Transactions are embedded; `NoSync` disables commit synchronization and is discouraged for normal use. [bbolt](https://pkg.go.dev/go.etcd.io/bbolt) | Viable bounded key/value store. A Go adapter must preserve the paired comparison, cross-process opening/locking and fixed errors. Language migration alone cannot establish correct persistence settings. |
| Erlang/Elixir Mnesia | `sync_transaction` waits for disk logging when disk is used, with configurable retries. [Mnesia](https://www.erlang.org/doc/apps/mnesia/mnesia.html#sync_transaction/3) | Relevant when BEAM supervision/distribution is required. Disk table configuration, retry policy and a request protocol would enlarge this single local store's operational surface without a replication requirement. |
| Managed-language or native fixed record with lock, temporary file, fsync and rename | File fsync alone does not ensure persistence of the containing directory entry. [Linux fsync](https://man7.org/linux/man-pages/man2/fsync.2.html) | Potentially a compact format, but a complete candidate must implement interprocess locking, paired compare/update, directory synchronization, crash recovery and ambiguous-write handling. No claim that a naive unlocked JSON replacement represents the best possible file implementation. Reimplementing this transaction machinery offers no established requirement advantage over a native engine. |

SQLite is retained because its native transaction/recovery protocol directly
covers the actual cross-process commit requirement without an application-owned
storage protocol or service. The binding choice is secondary: Python performs
bounded scalar/schema checks and invokes native transactions. Rust's static
checking or C#'s managed types would be useful in other hosts, but no missing
binding capability or measured bottleneck establishes a material win here.
Installed tooling, familiarity and rewrite expense are not the KEEP rationale.

## Corrective implementation and negative evidence

The prior connection setup selected DELETE journaling and FULL synchronization
without checking the resulting mode. SQLite documents that FULL in rollback
mode may lose the last transaction after a power loss on some filesystems.
EXTRA also synchronizes the directory after the journal is removed.
[SQLite synchronization modes](https://sqlite.org/pragma.html#pragma_synchronous)

The revised store checks that the journal setting returns `delete`, requests
EXTRA, and checks that the synchronous value is 3 before exposing the connection.
A missing or weaker result produces the existing fixed error. This applies to
initialization, reading and guarded/ordinary advances. The existing
`BEGIN IMMEDIATE` and return-after-COMMIT sequence is preserved.

Before implementation, a test observed FULL (2) at both initialization and update
commits. An injected binding that substituted OFF synchronization or MEMORY
journaling also allowed success. Those three failing assertions are retained in
the [audit evidence](../verification/fleet-floors-technology-audit-v2.json).
All now pass. These are configuration and failure-path tests, not simulated
physical power-loss measurements.

Two bounded child-process tests use `os._exit` to bypass Python cleanup: exiting
inside the uncommitted guard leaves the original pair; exiting immediately after
`advance` returns leaves the new pair. Reopening checks both fields together.
This tests process-death recovery while the OS remains running. It neither proves
power-loss durability nor certifies a disk/controller/filesystem combination.

The 48 focused floor/admission/plan/claim tests passed, along with Ruff and the
production-module Bandit scan. Existing corruption, missing-file, lock-contention,
failed-COMMIT, strict-value and no-reinitialization tests remain active. An initial
Ruff late-binding warning in the injected test adapter was corrected by explicitly
binding each test setting; no suppression was introduced.

## Boundaries and follow-up

The rollout journal is a separate store and retains its own pending technology
review; this change makes no cross-database atomicity claim. The known distinction
between FULL and EXTRA must be considered there when the chronological audit
reaches it. Do not substitute this decision for that review.

Reopen the engine/binding decision if independent-service hosting, replication,
a hard deadline, measured contention or a different process-sharing contract is
required. Real power interruption and storage-stack qualification remain external;
software tests and SQLite configuration are not substitutes for that evidence.
