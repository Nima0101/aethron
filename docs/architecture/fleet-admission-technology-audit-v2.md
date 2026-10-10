# Authenticated fleet admission: technology audit v2

Audit policy version: **2**. Component introduced in `e34e4f0`, reviewed through
`37dad34e11067ca8cb21570fbe5a33a55d289f20`. Decision: **KEEP the synchronous Python
adapter over native OpenSSL and SQLite, with a post-commit trusted-time check.**
This amends the pre-commit-only timing contract in `fleet-admission-v1.md`.
It completes the fourth component decision, not the lane audit.

## Constraints and decisive comparison

This local Linux control boundary authenticates a policy, checks caller-owned
trusted UTC, then commits two rollback floors before returning immutable
configuration. Its dependencies are versioned local verification and persistence
interfaces, not a network service. It must reject competing higher floors,
failed commits, malformed clocks and exclusive expiry. No automatic retries,
remote database, message delivery, actuator call or lasting authorization is
required. Cryptography and persistence execute in native libraries/tools; this
component orders calls and checks a constant number of bounded integers. There
is no established throughput, realtime, minimum RAM or hardware target against
which an unmeasured language speed claim could justify a migration.

Candidates were derived from embedded transactional coordination, typed control
flow, actor supervision and policy systems. Sources consulted 2026-10-10; the
assessments below are engineering judgments, not cross-language benchmarks.

| Candidate | Decisive evidence and fit |
| --- | --- |
| Python synchronous adapter, native SQLite/OpenSSL | The standard binding permits explicit SQL transaction control without implicit transaction opening when `isolation_level=None`. [Python 3.13 SQLite](https://docs.python.org/3.13/library/sqlite3.html). Direct calls provide an inspectable verify/check/commit/check sequence and strict integer checks without an additional request/response representation. Dynamic typing requires the negative tests retained here; annotations alone are not validation. |
| Rust with rusqlite and typed verifier | rusqlite offers explicit commit and rollback-on-drop defaults. [Transaction API](https://docs.rs/rusqlite/latest/rusqlite/struct.Transaction.html). Static types and ownership are credible advantages for larger native coordinators. They do not prove clock ordering or persistence after a late rejection; those remain explicit application obligations. A native in-process library is possible, so migration is not rejected on an assumption that Rust must be a subprocess. No native-only hosting, memory-safety defect in this small adapter, or measured bottleneck establishes a material win. |
| C# with Microsoft.Data.Sqlite | Transactions are serializable by default; lock acquisition can time out, and deferred transactions may need a complete retry after lock upgrade failure. [.NET transactions](https://learn.microsoft.com/en-us/dotnet/standard/data/sqlite/transactions). A synchronous managed implementation can satisfy this contract without a service. It still needs strict time admission, explicit commit handling and a final sample. CLR hosting and typed DTOs provide no demonstrated advantage for this bounded local callable, though they would be appropriate in a .NET host. |
| JavaScript/TypeScript with Node SQLite | Node exposes synchronous database operations, so an event-loop or promise race is not inevitable. [Node SQLite](https://nodejs.org/api/sqlite.html). Safe-integer validation covers the current UTC range; runtime checks remain necessary despite TypeScript. A correctly sequenced adapter is viable, but neither async scheduling nor a second runtime improves this blocking native transaction contract. |
| Erlang/Elixir with Mnesia | Transaction functions can restart after deadlocks, and the documentation restricts side effects within them. [Mnesia transaction semantics](https://www.erlang.org/doc/apps/mnesia/mnesia.html#transaction/1). Supervision and distributed transactions are useful for replicated orchestration. This component has neither requirement; retry semantics must not silently repeat trusted-clock observations or external verification. A bounded, correctly configured BEAM alternative is possible, but adds operational state with no demonstrated benefit here. |
| SQL-only stored policy or transactional outbox | SQLite serializes writers and explicitly reports busy commit/transaction outcomes. [SQLite transactions](https://www.sqlite.org/lang_transaction.html). SQL protects the paired floor update, but cannot by itself establish the caller's trusted clock or authenticate external policy bytes. An outbox is useful for durable dispatch; there is no dispatch in this component. The language-independent transaction boundary is retained rather than expanded. |

KEEP is based on the smallest trusted coordination surface satisfying the actual
host contract: explicit synchronous calls, no transport serialization, no retry
scheduler and native cryptography/storage. The comparison does not claim Python
is faster or statically safer than Rust/C#. Their plausible advantages do not
remove the observed defect or establish a missing requirement in this adapter.
Installation status, familiarity and rewrite cost are not selection criteria.
The existing verifier and database were separately reassessed; their mere prior
existence is not evidence of correctness. No required language migration remains
for this component.

## Executable correction and preserved failure evidence

Before this change, time was sampled before verification and immediately after
verification, followed by a potentially blocking durable floor commit and return.
The old document explicitly limited admission to that earlier sample. The audit
tightens the return boundary: resample trusted UTC after `advance` returns, require
a strict bounded integer no earlier than the pre-commit sample, and require the
policy's unchanged exclusive validity window. This catches time consumed by
writer contention, synchronization or scheduling before the final sample.

Four new test methods use real Ed25519 signatures and real SQLite transactions.
Before implementation, expiry at the third sample returned configuration; the
success trace contained only two clock calls; exhaustion of the clock sequence
was never observed. The malformed/backward-time test separately demonstrated
all six bad final samples being ignored. Its initial loop allowed the first
successful commit to make later attempts fail at the *initial* floor check; the
test was corrected to start each attempt at the committed floor, and all six
counterexamples were reproduced before implementation. This avoids false
coverage from rejection at the wrong boundary.

The corrected success trace opens a separate database connection at each sample
and observes the committed pair at the final sample. This proves the sample is
after commit, not just after an uncommitted UPDATE. Final expiry, invalid time,
clock rollback or clock exhaustion rejects with the fixed admission error but
does not restore old floors. Earlier verification or commit failure still leaves
this caller's update uncommitted. Existing concurrent version/time advances,
restart, signature failure and missing-store tests remain active.

These bounded counterexamples address the decisive temporal property directly;
a microbenchmark of a few integer comparisons would not compare native fsync or
cryptographic cost meaningfully. No contender is declared incapable based on a
naive prototype. See the [reproducible evidence record](../verification/fleet-admission-technology-audit-v2.json).

## Limits

The third observation is checked but is not itself persisted: persisting it
would create another commit requiring another final observation. The floor
stores the authenticated version and pre-commit verified time, not every clock
observation. A failure after commit may therefore advance floors. There is no
automatic rollback or retry. Scheduling can still delay return after the final
sample, and a concurrent admission can supersede the result. Consumers must
revalidate at their own operation boundary; this result is never a transferable
execution authority. Trusted clock/key compromise, restoring old database files,
physical power loss and hardware qualification are not tested or solved here.
