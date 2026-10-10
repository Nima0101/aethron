# Signed local wave claims: fresh V3 review

Decision: **KEEP synchronous/native transaction composition; FIX final commit
freshness gap.** Reviewed through `8ca703399fc3494643a7b83edb1cae9147101746`.
This is local inert bookkeeping only. No execution, transport or actuation is added.

## Constraints and open technology assessment

Authenticate a bounded private copy, match exact policy/artifact pins and journal
fields, check explicit provisioning policy, and serialize floors through journal
reservation. Inputs retain the snapshot and journal bounds. Floor and journal
stores have separate commits; unknown outcomes must never trigger automatic
retry or evidence deletion. Caller owns time, key and protected directories.
No target ABI, deadline, throughput or resident-memory budget is provided.

Official sources checked 2026-10-10 inform this engineering comparison:

| Candidate | Decisive properties |
| --- | --- |
| Python with native SQLite and existing crypto | [Context manager ordering](https://docs.python.org/3/library/contextlib.html) makes body and exit distinct. [SQLite transactions](https://sqlite.org/lang_transaction.html) serialize writers; commit remains a separate potentially delaying operation. The small adapter can expose this ordering explicitly without a scheduler or retry protocol. |
| Rust/rusqlite | [Explicit commit/rollback](https://docs.rs/rusqlite/latest/rusqlite/struct.Transaction.html) and typed lifetimes can make resource ownership clearer. A native library need not introduce IPC. Types do not ensure a clock sample occurs after the final commit. |
| C#/.NET SQLite | [Serializable transactions](https://learn.microsoft.com/en-us/dotnet/standard/data/sqlite/transactions) support local writer exclusion. Managed typing and explicit disposal are viable; deferred retries need care around timestamps and externally visible reservations. |
| Erlang/Elixir Mnesia | [Transaction contexts](https://www.erlang.org/doc/apps/mnesia/mnesia_chap4.html) provide a credible distributed transactional runtime. Retried transaction functions and side effects need explicit handling; distribution is not required for this local boundary. |
| Single SQLite database or transactional outbox | One database could atomically contain both records. That changes global-floor/per-plan storage ownership and recovery semantics, and still needs post-commit expiry validation. An outbox is useful for dispatched work, but this component performs no external dispatch and must not acquire one merely to solve a time-check ordering error. |

KEEP selects an inspectable synchronous adapter over native primitives. The
observed defect is ordering, not a demonstrated runtime limitation. Alternatives
remain viable but no measured bottleneck or missing hosting property establishes
a material migration winner. Familiarity, installed tools and rewrite cost are
not criteria. No alternative-runtime performance benchmark or speed ranking is
claimed. A new deployment ABI or budget would reopen the decision.

## Reproduced defect and correction

The fourth clock sample followed journal commit but preceded floor-guard exit.
That exit performs the floor COMMIT, which can delay the call past expiry. The
old implementation returned slots without observing that interval.

Three new tests failed against the unchanged implementation: final expiry at
2000 returned slots, a clock exhausted after four observations returned slots,
and a positive trace recorded four rather than five observations. No environment
errors or skips occurred in this RED run. The correction saves the fourth sample
and validates a fifth sample after the floor guard exits, using the unchanged
strict bounds, monotonicity and exclusive expiry rules.

Late rejection preserves the committed floor and running journal reservation;
it never clears either. A positive test opens fresh readers at the fifth sample
and observes both commits. An additional backward-fifth-sample test rejects and
preserves both stores. Existing tests still distinguish pre-floor-commit rejection
and commit failure, where the provisional floor update rolls back. Normal success
fixtures now supply the fifth observation.

Fifteen claim tests and 49 combined claim/plan/floor tests pass. Ruff, formatting
and production Bandit pass. [Source-bound evidence](../verification/fleet-claim-review-v3.json)
retains the three RED outcomes and current source hashes. Reproduce with:

```sh
PYTHONPATH=integrations/edge:build/fleet-linux-deps:tests/integration python3 -W error::ResourceWarning -m unittest test_fleet_claim test_fleet_plan test_fleet_floors -v
```

## Limits and next component

The last sample is checked rather than persisted. Later scheduling delays and
competing admissions still invalidate any interpretation as lasting authority.
The result is a bookkeeping reservation, not an execution token. The caller's key
selection is not an implemented revocation service. There is no cross-database
atomicity, automatic retry, installer or remote receipt handling. No hardware,
CNSA/MLS, real-time or five-nines qualification is established. Insufficient
information for tactical deployment. Next earliest component: the uncommitted
P11 aggregate-health lease and authenticated envelope. Full-lane completion
remains unclaimed.
