# Local rollout journal: fresh V3 review

Decision: **KEEP native SQLite / bounded Python; FIX recovery and technology
claims and add acknowledgment-error coverage.** Reviewed through
`aef388b58a7a3895a85811e5dad186895af26e34`. Production code and schema are unchanged.
Earlier V3 components have no intervening production changes in committed HEAD;
the separate uncommitted health lease remains part of the pending P11 review.

## Constraints and current candidate comparison

One protected local plan has at most 1024 slots, one running wave, sticky terminal
failures, content pins and atomic revision/time progression. Malformed or missing
state must not reset. The record is capped at 16 KiB and the database admission
check at 1 MiB. These are not total memory/disk quotas. No target ABI, hardware
memory budget, processing deadline, distributed replication or query workload
has been supplied. The 100 ms lock timeout is not an operation deadline.

Official sources checked on 2026-10-10 support the following engineering
assessment. Candidate merits are not inferred from tooling availability.

| Candidate | Decisive property for this boundary |
| --- | --- |
| SQLite native engine with Python whole-record validation | [Atomic commit](https://sqlite.org/atomiccommit.html) provides recovery for one transaction covering the complete record. [EXTRA synchronization](https://sqlite.org/pragma.html#pragma_synchronous) adds directory synchronization in DELETE mode. The bounded validator checks global wave/revision invariants before writing. |
| Rust/rusqlite with typed states | [Explicit commit and rollback](https://docs.rs/rusqlite/latest/rusqlite/struct.Transaction.html) support the same engine semantics. Ownership and enums can prevent some programming mistakes; persisted JSON and cross-slot invariants still need validation. This can be an in-process library, not necessarily IPC. |
| C#/.NET with SQLite | [Serializable transactions and writer concurrency](https://learn.microsoft.com/en-us/dotnet/standard/data/sqlite/transactions) provide the needed local atomicity. Typed records are credible, but deferred retries must preserve the compare-and-set contract. No managed service is intrinsically required. |
| Normalized SQL or SQLite JSON functions | [JSON support](https://www.sqlite.org/json1.html) permits native inspection. Per-slot rows allow selective updates, but global wave ordering and revision consistency span rows. The capped record has no supplied selective-query or update-pressure requirement that establishes a normalization win. |
| Rust redb | [Immediate durability](https://docs.rs/redb/latest/redb/enum.Durability.html) is available. Engine substitution still needs verified process-sharing, recovery, fixed-error and state-machine parity. Static types do not establish application state reachability. |
| Erlang/Elixir Mnesia | [Transactions and access contexts](https://www.erlang.org/doc/apps/mnesia/mnesia_chap4.html) support transactional distributed data. [Synchronous transactions](https://www.erlang.org/doc/apps/mnesia/mnesia.html#sync_transaction/3) support disk-log synchronization with appropriate tables. Distribution/supervision are useful when required; retry semantics must not imply repeating external operations. |

KEEP follows from the native transaction/recovery model and a small bounded
synchronous validator directly meeting this local contract. Typed alternatives
are credible; no measured binding bottleneck, hosting constraint or missing
property establishes a material migration winner. No alternative-language speed
benchmark was run and no speed ranking is claimed. A supplied target runtime,
resource budget or replicated-service requirement would reopen the choice.

## Findings and verification

The main contract still recommended FULL below an amendment specifying EXTRA;
it now consistently describes the verified profile. It implied every commit
failure preserves old state, although post-commit failures can retain new state.
It also implied alternative bindings require a new executable and called slots
anonymous. Those claims are corrected: local ordinals minimize fields but do not
prevent association through an external mapping.

The new four-case test wraps a real SQLite connection and raises a fixed injected
`OperationalError` before or after the actual COMMIT, for both claim and failure
recording. The public error omits the injected detail. A fresh connection finds
the old snapshot before commit, or the whole new state and revision after commit.
Committed reservations cannot be claimed again. A recorded failure cannot be
rewritten to success; settling another running slot preserves that failure.
This simulates acknowledgment ambiguity, not a claim about every SQLite I/O error.

All 15 journal tests pass, including four child-process death cases and 9216
comparisons between the validator and independent reachable-state exploration
for four slots. The latter is not a proof over all 1024 slots. New error cases
pass existing production code; no artificial red-to-green implementation claim
is made. The [V2 negative evidence](../verification/fleet-rollout-technology-audit-v2.json)
is unchanged. [V3 evidence](../verification/fleet-rollout-review-v3.json) binds
current source/test bytes. Reproduce with:

```sh
PYTHONPATH=integrations/edge:build/fleet-linux-deps:tests/integration python3 -W error::ResourceWarning -m unittest test_fleet_rollout -v
```

## Assurance and next boundary

The store authenticates neither callers nor receipts and grants no installation
or actuation authority. State can outlive expiry for evidence; it is not a fresh
authorization token. There is no reset, automatic retry, external exactly-once
execution, cross-database atomicity or protection against a privileged old-backup
restore. Tests leave the OS running and do not qualify power loss. No MLS/CNSA,
hard-real-time, five-nines or physical platform assurance follows. Insufficient
information for tactical deployment. Next earliest component: authenticated
snapshot-to-plan binding. Full-lane completion remains unclaimed.
