# Portable consumer corpus binding — review v3

Baseline: `42c787f24afe387565cc15c94afd457096999d9c`. The fresh walk reread
declaration admission, artifact matching and campaign coverage before revisiting
portable consumer evidence. Twenty focused baseline methods passed, including
declaration/artifact/campaign negative controls and the previous CLI shutdown fix.
No new production admission defect was demonstrated. The consumer runner had an
evidence-integrity mismatch: retaining case IDs while replacing negative inputs
and their expectations with the complete case made all three consumer tests pass.
Names alone did not preserve the advertised negative coverage.

## Constraints and decision

This is an offline source-checkout test of bounded synchronous byte APIs, with
a repository-owned JSON fixture capped at 32 KiB. It must preserve reviewed inputs,
expected negatives and exact Python result types. It does not accept uploads,
authenticate producers, install a product or execute devices. There is no native
ABI, hard deadline, bandwidth target or measured allocation constraint here.

| Candidate | Decisive property for this boundary |
|---|---|
| JSON plus Python unittest and hashlib | Reviewable portable fixture; hash the exact already-bounded bytes before parsing; directly inspect the API objects without serialization losing their types. |
| CUE validation plus exported JSON | Credible independent constraint language. Shape constraints alone still allow a self-consistent replacement; exact fixture identity needs a separate commitment. Useful if a generated constraint matrix becomes required. |
| F#/C# with SHA256.HashData | Credible independent consumer host supporting byte and stream hashes. It can check fixture identity, but serialized consumption cannot observe original Python runtime types. Reassess for an independent installed consumer. |
| CBOR corpus plus a consumer | Native byte-string representation is useful for larger binary corpora. Format replacement does not preserve the identity of reviewed cases by itself; current tiny payloads favor direct textual review. |

**KEEP JSON and direct Python tests; FIX exact corpus admission.** This judgment
rests on byte preservation and direct runtime-type observability, not installed
tooling, familiarity or rewrite cost. No throughput ranking or cross-language
execution is claimed. Sources inspected on 2026-10-10:
[JSON](https://www.rfc-editor.org/rfc/rfc8259),
[Python hashlib](https://docs.python.org/3.13/library/hashlib.html),
[CUE validation](https://cuelang.org/docs/concept/how-cue-enables-data-validation/),
[.NET SHA256](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.sha256.hashdata?view=net-9.0),
and [CBOR](https://www.rfc-editor.org/info/rfc8949).
The first CBOR fetch failed; the linked official endpoint succeeded on follow-up.

## Change and evidence

The runner compares the same bounded byte buffer it parses to a literal SHA-256
pin. It never derives that pin from the current fixture at runtime. V1 fixture
bytes remain unchanged. A future changed corpus needs a reviewed new version,
not an automatically regenerated pin. This detects fixture replacement under
trusted runner code; it cannot defend against coordinated edits to both the
runner and fixture or attest execution.

Two new methods exercise six replacements: each of the five negative cases alone
and all five together. Each preserves IDs and supplies internally matching passing
inputs/expectations. Before correction all escaped detection: six assertion
failures, zero execution errors. After correction each causes all three real
consumer methods to fail. An identical-byte copy at another path still passes.
All 24 focused consumer/bundle/reference methods pass; Ruff, formatting and
targeted Bandit pass with zero findings.

The existing count-type controls explicitly substitute a temporary fixture's pin
inside their test context, so the new gate cannot mask the old type assertions.
Disabling only the type checker still causes twelve expected failures across
those two control methods, with zero errors or skips. Real consumer execution
never overrides its pin. No production source, schema, threshold, expected finding
or qualification flag changed. Historical evidence remains unchanged.

This is partial report conformance on Linux CPython 3.13.5, not full fuzzing,
installed-product acceptance, independent consumer execution or hardware evidence.
The hosted workflow was read: discovery covers these methods, but this correction
has not run remotely. Remaining audit tooling and hosted configuration review are
next; P15/P19 executable software and external physical gates remain unfinished.
