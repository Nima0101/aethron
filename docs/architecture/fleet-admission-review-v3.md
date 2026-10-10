# Authenticated fleet admission: fresh V3 review

Decision: **KEEP synchronous adapter; FIX failure-contract documentation and
coverage.** Reviewed through `39fc3722294857c269781748301fe28fe166bc9d`.
Production code and versioned interfaces are unchanged. The review follows health,
signed policy and persistent floors; rollout journal is the next component.

## Constraints and technology assessment

The boundary authenticates local bounded configuration, rejects version/time
rollback and returns only after a successful floor commit and final trusted-time
check. It has no transport, installation, distributed coordinator or real-time
scheduler. Time and storage are trusted caller dependencies; malformed inputs
must not produce configuration or reset state. No target hardware deadline,
resident-memory budget or throughput requirement was supplied.

Official sources were consulted on 2026-10-10. The comparison concerns the whole
admission boundary, not language popularity or installed tooling.

| Candidate | Decisive properties and evidence |
| --- | --- |
| Python with native OpenSSL/SQLite | The [SQLite binding](https://docs.python.org/3.13/library/sqlite3.html) exposes explicit transactions. Sequential calls make authentication, commit and three clock samples inspectable without a scheduling or retry layer. The wrapper handles bounded validation; native dependencies own crypto and transaction machinery. |
| Rust with rusqlite/native crypto | [Transactions](https://docs.rs/rusqlite/latest/rusqlite/struct.Transaction.html) support explicit commit and rollback. Ownership and typed errors are credible advantages for a larger native host, but do not themselves ensure post-commit time sampling. Native in-process integration is possible; IPC is not required. |
| C#/.NET with Microsoft.Data.Sqlite | [Transactions](https://learn.microsoft.com/en-us/dotnet/standard/data/sqlite/transactions) support the required local serialization. Deferred transaction retries need deliberate treatment because clock observations and authentication must remain bound to the attempted commit. No managed service is inherently required. |
| Node/TypeScript with node:sqlite | The [synchronous database API](https://nodejs.org/api/sqlite.html) can compose this ordering. Safe-integer checks, strict parsing and error mapping need parity; an event loop does not establish a deadline. Current documentation is not evidence of this host's supported Node API version. |
| Erlang/Elixir with Mnesia or a SQLite binding | [Mnesia transactions](https://www.erlang.org/doc/apps/mnesia/mnesia.html#transaction/1) may restart transaction functions; side effects require care. Supervision/distribution can be valuable for a distributed service, but neither is required by this local call. A BEAM implementation can avoid automatic retry; its runtime alone does not establish freshness. |

KEEP is an engineering judgment: the existing bounded synchronous adapter already
expresses the required ordering directly and delegates crypto/storage to native
implementations. Alternatives offer viable hosting and type-system choices, but
no observed binding bottleneck or missing runtime requirement establishes a
material win for this component. This is not a speed ranking, and no comparative
performance benchmark was run. Familiarity, rewrite expense and tool availability
are not decision criteria. A target ABI, memory/deadline budget or measured
bottleneck would reopen the assessment.

## Findings and executable checks

The main contract incorrectly said every rejection leaves floors unchanged,
omitted the final sample in its numbered ordering, and implied native alternatives
require a separate process. Those claims are corrected. Its future-tense
implementation plan is replaced with current results and explicit limitations.

A new test injects `OSError`, `RuntimeError` and `ValueError` separately at each
of the three clock samples. All nine cases return exactly
`invalid_fleet_admission`, omit injected private diagnostics and perform no retry.
Fresh SQLite readers observe `(1, 900)` for first/second-sample failures and
`(3, 1001)` for the post-commit failure. Thus an error cannot authorize restoring
old floors. The third observation is intentionally not another persisted floor.

All 16 admission tests pass, including the earlier real-signature, concurrent
advance, commit-failure and post-commit expiry checks. The added cases pass the
existing production implementation: no manufactured red-to-green claim is made.
The [V2 negative evidence](../verification/fleet-admission-technology-audit-v2.json)
remains intact. Reproduce with:

```sh
PYTHONPATH=integrations/edge:build/fleet-linux-deps:tests/integration python3 -m unittest test_fleet_admission -v
```

## Assurance boundary

The call returns point-in-time configuration, not permission to execute an
operation. It does not freeze competing admissions, persist every clock reading,
provide cross-database atomicity or impose an end-to-end deadline. Fixed errors
cover listed expected exceptions from trusted dependencies, not arbitrary hostile
Python objects. No actuation, tactical transport, MLS/CNSA, hardware durability,
real-time or uptime qualification is established. Insufficient information for
tactical deployment. Full-lane V3 completion remains unclaimed.
