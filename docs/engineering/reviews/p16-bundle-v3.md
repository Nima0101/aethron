# P16 bundle verification review v3

Baseline: `3d30cad4d224251f71673e955828fe3fb9a08922`. Reviewed 2026-10-10.
Decision: **KEEP immutable snapshot composition; FIX boundary coverage; CLARIFY claims**.
No production behavior, task kind, signature profile or fixture bytes changed.

## Requirements and technology reassessment

The component binds bounded, already-local exact byte snapshots to an externally
provisioned task digest and reuses the public passport/evidence verifiers. The required
properties are stable bytes across repeated parsing and hashing, closed admission,
caller-controlled trusted policy/time floors, preservation of negative outcomes, and
no execution authority. There is no transport, device SDK, service SLA, hard deadline or
specified target RAM envelope. The 1,245,184-byte input ceiling does not bound interpreter
objects or total process memory. This review does not optimize an operational pipeline.

| Candidate | Decisive properties |
|---|---|
| Python exact bytes and tuple | [Built-in types](https://docs.python.org/3.13/library/stdtypes.html#bytes-objects) supply immutable bytes and containers. Exact-type admission excludes caller-defined overrides and mutable buffers. The bounded composition uses native hashing/signature operations without maintaining another trust-policy implementation. |
| Rust immutable borrowing | [Borrowing rules](https://doc.rust-lang.org/book/ch04-02-references-and-borrowing.html) prevent overlapping safe mutable and shared borrows. This is a credible native snapshot boundary; it does not by itself authenticate pins or establish a hardware deadline. Foreign or unsafe memory requires separate ownership guarantees. |
| Java/Kotlin with protobuf ByteString | [ByteString](https://protobuf.dev/reference/java/api-docs/com/google/protobuf/ByteString) offers immutable byte content and immutable slices. This is a credible managed alternative; it does not require changing the v1 wire representation to Protobuf. The older mutable-buffer comparison must not be read as ruling out JVM immutability. |
| C# with owned storage and ReadOnlyMemory | [ReadOnlyMemory](https://learn.microsoft.com/en-us/dotnet/api/system.readonlymemory-1?view=net-10.0) provides a read-only view, including over arrays. Read-only access through that view does not establish exclusive ownership of its backing array. An adapter must establish an immutable snapshot or prevent mutation through aliases. |

KEEP the current bounded adapter: exact immutable inputs and composition through the
public verification boundary satisfy these requirements without additional trust logic.
Other candidates can satisfy them too; no measured deployment requirement establishes a
material advantage sufficient to choose a migration here. This is not evidence that
Python is fastest or has the smallest memory footprint. Incumbency, installation and
rewrite cost are not decision criteria. Reopen selection for a concrete target, but do
not substitute desktop timings for physical qualification. Preserve the v1 byte and
rejection contracts in any migration.

## Findings and retained evidence

Eight original bundle tests passed. Added three tests cover all three revocation lists
for both task kinds after a positive binding (six combinations), passport-limited expiry
and rejection at its exclusive boundary, and a failure while hashing the last blob.
Rejection checks require absent digests, revision, expiry and evidence, plus all three
authority/qualification flags false. The positive result also checks the distinction
between its signed-payload digest and the task's envelope digest. Eleven bundle tests
pass against unchanged production code; no production RED/fix is claimed.

The prior task review incorrectly described only key and statement revocation lists.
`passports.verify` also enforces `revoked_evidence` against every signed evidence reference,
including in passport-only bundles. This review corrects that earlier documentation,
retains the old task results as historical evidence, and tests the actual behavior.
The earlier note's word “independently” was insufficient to communicate the distinction
between enforcing a supplied revocation list and discovering revocations externally.

The bundle contract now explicitly states that its trusted time is a caller-supplied
snapshot, its policy is not refreshed automatically, and saved results do not expire
themselves. Replacing policy bytes requires a newly provisioned task pin. Byte-length
bounds do not prove memory, scheduling or latency bounds. Native in-process callers and
managed immutable containers remain credible; no forced IPC/copy assumption is used.

Reproduce in the pinned conformance environment:

```sh
python -m unittest discover -s tests -p test_interop_bundles.py -v
python -m unittest discover -s tests -p 'test_interop*.py'
python -m unittest discover -s tests -p 'test_passport*.py'
```

[Source bindings and results](p16-bundle-v3-results.json) record the executed checks.
No hardware, MLS, CNSA, availability or real-time qualification is established.
Next earliest component: P16 direct federation. V3 review remains incomplete.
