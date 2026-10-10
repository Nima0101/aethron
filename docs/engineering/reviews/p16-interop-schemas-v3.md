# P16 task/federation structural conformance review v3

Baseline: `8edce6f5e6cd877b2c836da14a1947f7f06a984f`. Reviewed 2026-10-10.
Decision: **KEEP versioned JSON and bounded runtime admission; FIX missing schemas**.

## Constraints and technology selection

These are offline software-verification descriptions, not operational commands. Consumers
need language-neutral, closed JSON shapes, bounded collections, exact kind-dependent
budgets, safe numeric ranges and no remote schema resolution. Runtime authentication and
lexical parsing remain separate. No hardware class, hard deadline or throughput target is
specified; this decision makes no comparative speed or physical qualification claim.

| Candidate | Evidence and decisive fit |
|---|---|
| JSON Schema 2020-12 | The [validation vocabulary](https://json-schema.org/draft/2020-12/json-schema-validation) provides required properties, numeric and collection limits, constants and uniqueness. It describes the existing JSON structure without changing the pinned wire bytes. Mathematical integers cannot distinguish integer-valued float lexemes. |
| CUE | [CUE validation](https://cuelang.org/docs/concept/how-cue-enables-data-validation/) offers constraints and unification for structured data. It is a credible non-incumbent language for richer cross-field configuration validation. This deliverable needs a directly consumable structural JSON contract; selecting CUE would require an additional distribution/evaluation or schema-export contract, with lexical and trust checks still separate. |
| Protocol Buffers | The [proto3 guide](https://protobuf.dev/programming-guides/proto3/) defines typed messages and generated language APIs. It is credible when typed binary messages are required. These contracts instead pin existing canonical JSON bytes, and protobuf fields alone do not express this full structural validation profile. No binary-wire requirement justifies migration. |

Choose self-contained JSON Schema artifacts with offline conformance tests. Keep the
existing optional Python validator test tool: its no-retrieval registry and independent
runtime comparisons exercise these contracts without putting it in production admission.
This is contract fit, not incumbent-language protection, installed-tool convenience or a
claim that another language is slower. No production runtime code or dependency changes.
The broader validator comparison remains in [the conformance review](p16-conformance-v3.md).

## Review and correction

Freshly inspected parser/canonicalization, task validation and federation admission preserve
bounded immutable bytes, safe integer tokens, false authority flags and direct scope.
The schema inventory still covered only passport payload/envelope/policy. Publish two
additional structural contracts and test them against the existing runtime and portable
fixtures. Frozen thresholds and fixture bytes remain unchanged.

Five new test methods cover all 15 portable task/federation cases with real positive and
negative runtime results; closed root/peer shapes; scalar and identifier rejection;
kind-dependent evidence/budget limits; collection boundaries; and explicit semantic gaps.
The existing self-contained-schema test now covers all five artifacts. Six assertion
failures (zero errors) precede schema creation. Afterwards 12 schema methods pass; the
passport family has 61 passing methods and interop runtime has 43, with no skips.
The existing hosted workflow already selects the test file and both contract paths;
this is local evidence, not an assertion of a new hosted run.

Structural success intentionally leaves positive interval length and TTL, same-domain
peers, repeated remote-domain names with different metadata, and float lexical forms to
the normative runtime. Pins, freshness, revocation and scope are checked by real public
verifiers in the portable comparisons. No structural success grants authority or qualifies
evidence. Reference retrieval is disabled; schemas contain no external references.

[Source bindings and results](p16-interop-schemas-v3-results.json) record this local slice.
Next: reconcile remaining cross-phase consumer conformance against published contracts.
P16/P17/P18 and the whole-lane retrospective audit remain incomplete.
