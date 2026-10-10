# Committed version/time floors: fresh V3 review

Decision: **KEEP SQLite/Python; FIX stale durability and outcome documentation
and add a missing crash-boundary test.** Subject: `FleetFloorStore` through
`18ed24b882025996c2ac035ed936b4c87121eb05`. Production behavior and database
schema remain unchanged. Earlier health and signed-policy decisions were checked
for intervening changes; later admission, rollout and P11 reviews remain open.

## Requirements and current technology assessment

One strict version/time pair must survive process restart and be compared and
updated atomically across local writers. Reads must not initialize defaults;
malformed state and lower values must fail closed. The directory is protected,
local and not NFS. There is no remote query service, replication requirement,
deadline or supplied hardware memory budget. The 100 ms SQLite busy timeout
bounds a lock-wait mechanism, not end-to-end I/O or scheduling. The 1 MiB database
check does not measure or cap SQLite's complete memory or journal footprint.

Primary sources were rechecked on 2026-10-10. Assessments are engineering
inferences for the complete storage boundary, not unmeasured speed rankings.

| Technology | Evidence and decisive property |
| --- | --- |
| SQLite native engine + Python binding | [Transactions](https://sqlite.org/lang_transaction.html) provide writer serialization and paired commit. [Synchronization modes](https://sqlite.org/pragma.html#pragma_synchronous) distinguish EXTRA's journal-directory sync from FULL. Bounded Python validation composes with native recovery; correctness depends on settings and storage assumptions, not the wrapper language. |
| SQLite through Rust or C# | A different binding preserves the engine's transaction model. The [previous source comparison](fleet-floors-technology-audit-v2.md) includes .NET transactions. Both are credible local bindings, not necessarily servers. No measured wrapper bottleneck or missing hosting requirement establishes a material win. |
| LMDB with native/language binding | [LMDB](https://lmdb.readthedocs.io/en/release/) supports transactional memory mapping and one writer; sync/metasync options matter. Map capacity is not resident-memory consumption. A candidate must preserve fixed-schema rejection, paired comparison and multi-process locking, not merely store two numbers. |
| Rust redb | [Immediate durability](https://docs.rs/redb/latest/redb/enum.Durability.html) is available. Full process-sharing, fixed-error and recovery parity still need validation for this interface. Strong native typing alone does not establish those semantics. |
| Erlang/Elixir Mnesia | [Synchronous transactions](https://www.erlang.org/doc/apps/mnesia/mnesia.html#sync_transaction/3) can wait for disk logging when disk tables are configured. Distribution and supervision are useful when required; this one-row local store has no distributed runtime or retry protocol requirement. |
| Go bbolt or a fixed record with locks/fsync/rename | Credible embedded alternatives retained from the [V2 assessment](fleet-floors-technology-audit-v2.md). Both require explicit commit/recovery policy. A fixed-file design must own interprocess locking, directory sync and uncertain outcomes; a naive JSON replacement is not a fair candidate. |

KEEP follows from native transaction/recovery machinery meeting the specified
cross-process contract without an application-owned storage protocol. Python's
role is bounded input/schema checks and an immutable return value. No language
receives preference for familiarity, availability or rewrite expense. A different
host ABI, replication requirement, deadline or measured binding bottleneck would
reopen the choice. No alternative implementation benchmark was run in this review;
absence of such a benchmark is not evidence that alternatives are slower.

## Findings and executable evidence

The main contract still prescribed FULL, despite production checking DELETE and
EXTRA on every connection. That stale recommendation is corrected and existing
configuration-failure tests remain active. The historical V2 audit/evidence is
preserved rather than rewritten as if the old implementation never existed.

Outcome wording also needed narrowing. A failed or unobserved request is not
proof that a transaction rolled back. The added test wraps a real SQLite
connection, executes the real COMMIT, then terminates the child with `os._exit(75)`
before `advance` returns. A marker after the call remains absent. A fresh reader
finds the complete `(5, 2000)` pair, and a lower update is rejected. This rules
out interpreting missing success as permission to restore the old `(3, 1000)`
pair. It does not simulate every SQLite I/O error or power loss.

The production code already behaves correctly for this case, so there is no
manufactured failing implementation test or language migration. The correction
is an executable regression check plus accurate recovery documentation. Existing
pre-COMMIT failure and pre/post-commit process-death tests preserve the distinction
between rollback and committed state. All 18 focused floor tests passed.

[Evidence](../verification/fleet-floors-review-v3.json) records source hashes,
the precise failure injection and limits. Reproduce with:

```sh
PYTHONPATH=integrations/edge:build/fleet-linux-deps:tests/integration python3 -m unittest test_fleet_floors -v
```

## Integration and qualification

The guarded context yields provisional floors and must exit successfully before
local success is reported. It does not grant operation authority or atomically
commit another database. The caller authenticates input and supplies trusted
time. Restore of an old valid database, malicious same-user modification and
storage hardware dishonoring sync are not solved by this library.

No MLS/CNSA, hard-real-time, five-nines or physical-durability qualification is
established. Consumers must not infer scene evidence, physical readiness or
actuation authority from a version/time pair. Insufficient information for
tactical deployment. Next earliest review: authenticated admission with persistent
floors. Full-lane V3 completion remains unclaimed.
