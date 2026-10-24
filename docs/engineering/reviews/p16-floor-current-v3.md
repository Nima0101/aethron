# P16 fresh review and pending floor-store correction

Baseline `8c6ccdb9c4e9fa4aa49f9644398e47e5305973da`, plus the inherited staged
policy-floor store. Read the authoritative owner policy and V3 order again on
2026-10-10. Prior review decisions are inputs, not completion evidence. No forward
P17/P18/P19 component is added in this slice. Their untracked plans remain pending.

## Earliest-component reassessment

The deployment constraint remains an offline library accepting at most 65536 immutable
bytes and depth eight. Closed ASCII schemas, safe integer lexical bounds, duplicate
rejection, exact canonical bytes, native signature verification and explicit trusted
time/policy inputs are required. No identified embedded hardware, WCET/RSS target or
high-volume workload supplies a native-runtime migration criterion.

| Component | Fresh evidence and decision |
|---|---|
| Parser/canonicalization | KEEP Python lexical callbacks after reading the implementation and running lexical/schema cases. [Python JSON](https://docs.python.org/3/library/json.html) and [Erlang/Elixir OTP JSON](https://www.erlang.org/doc/apps/stdlib/json.html) both expose number/object callbacks; [C#/F# Utf8JsonReader](https://learn.microsoft.com/en-us/dotnet/standard/serialization/system-text-json/use-utf8jsonreader) exposes token spans. [Rust serde_json](https://docs.rs/serde_json/latest/serde_json/) is another credible bounded adapter basis. Python callbacks directly express this contract without a custom tokenizer. Streaming/native paths need their own duplicate/canonicalization rules and a demonstrated resource benefit; no such benefit is established here. |
| Signature/trust/expiry/revocation | KEEP explicit application gates plus the native-backed [cryptography Ed25519 API](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/). [Java/Kotlin Signature](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/Signature.html) and [C/libsodium](https://doc.libsodium.org/public-key_cryptography/public-key_signatures) are serious alternatives. A primitive replacement alone does not establish issuer, scope, revocation, policy freshness or authority. The actual admission tests cover these independently of the primitive and reject unsupported crypto. No comparative latency or certification claim. |
| Independent pinned policy | KEEP complete schema validation and exact immutable-byte hash binding. It must accept revoking policies even when every passport fails, and must receive external pins/time floors. The parser alternatives above can implement this too; another runtime supplies neither trusted enrollment nor persistence. Direct reuse preserves the same lexical contract without an IPC serialization boundary. Current policy tests pass; no new stateless defect found. |
| Pending local floor store | KEEP native SQLite transactions with Python binding; FIX unchecked effective page limit and test connection cleanup. Fresh [rusqlite](https://docs.rs/rusqlite/latest/rusqlite/), [.NET SQLite transactions](https://learn.microsoft.com/en-us/dotnet/standard/data/sqlite/transactions) and [Erlang Mnesia](https://www.erlang.org/doc/apps/mnesia/mnesia_chap4.html) review supports the alternatives in the [ADR](../../decisions/p16-policy-floor-store-v1.json). SQLite bindings share the engine's locking/durability semantics. A separate validator/runtime has no established benefit for one local metadata row; atomic JSON would require a separate lock/journal protocol. Mnesia's broader database model is not required for this isolated scope. LMDB documentation retrieval failed again, so no adverse LMDB guarantee is inferred. |

These are requirement-bound selections, not language speed rankings. Alternative
implementations were researched, not benchmarked or claimed to have contract parity.
The existing C4 views in the parser review and floor-store contract remain applicable.
No scope here grants authority, provides sensor fusion or qualifies tactical deployment.

## Executable correction

The inherited implementation requested `PRAGMA max_page_count=16` but discarded the
result. [SQLite documents](https://www.sqlite.org/pragma.html#pragma_max_page_count)
that this cannot reduce the limit below an existing database's page count. A real
512-byte-page fixture, retaining free pages after a scratch table is dropped, remains
under 65536 bytes with the expected schema/row but exceeds sixteen pages. Opening it
incorrectly succeeded. The new regression initially failed with `FloorStoreError not
raised`; it now passes after checking the effective result. Rejection preserves the
file bytes. No schema, threshold, policy floor or public method signature changed.

The prior focused log also contains `ResourceWarning: unclosed database` messages:
SQLite connection context managers commit/rollback but do not close. Test-owned
connections now use explicit `contextlib.closing` around transaction contexts. The
production helper already closes in `finally`. The old log is retained.

The fresh focused run passes 79 methods without skips, failures or resource warnings:
16 real-file store methods, 26 passport methods, 9 policy/lexical methods, 4 ADR
methods, 7 packaging-input methods and 17 install-checker methods. Ruff/format and
unexcluded Bandit on the new production module and changed package helpers pass.
See [source-bound results](p16-floor-store-v1-results.json) for exact logs and commands.
The tests run from source; no installed distribution or hosted execution is claimed.

The new store remains a local protected-filesystem helper. Whole-file restoration can
roll back floors; the retained negative test demonstrates that limitation. No hardware
power-loss, clock authenticity, MLS/CNSA, availability or real-time qualification.
Insufficient information for tactical deployment.

Next earliest unreviewed component: evidence-byte binding, followed by task, bundle,
federation, inbox, schemas/consumer tooling and the remaining owned implementation
inventory. Installed-package persistence conformance remains a separate executable
gap. No audit-complete marker or phase/lane completion is issued.
