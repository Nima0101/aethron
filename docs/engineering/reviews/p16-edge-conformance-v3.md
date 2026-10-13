# P16 published edge evidence conformance v3

Baseline: `93b916427dfd8ae8e7301d0a37bd2dabed0b9eda`. Reviewed 2026-10-10.
Decision: **KEEP bounded byte binding; FIX cross-contract coverage gap**.

The schema bridge matches its parent, seven recorded file hashes and noreply identity.
The fresh source review of evidence, bundle and inbox boundaries confirms they do not
interpret arbitrary evidence content or map scene clocks. No production defect is
asserted. Prior parser and conformance results are evidence inputs, not phase completion.

## Requirements and candidate comparison

This deliverable checks immutable, synthetic, non-identifying fixtures offline. It must
consume a published producer schema, preserve exact evidence bytes, exercise real P16
signature/bundle validation, disallow remote reference retrieval and retain expected
negative outcomes. It must not implement a second scene model or sensor runtime. No
hardware timing, memory SLA or runtime throughput ranking is part of the requirement.

The [OpenAPI 3.1.1 Schema Object](https://spec.openapis.org/oas/v3.1.1.html#schema-object)
uses JSON Schema semantics. The selected snapshot and recommendation use ordinary
structural assertions and local component references. This test is not a complete
OpenAPI validator or an execution of the peer's Pydantic implementation.

| Candidate | Decisive fit |
|---|---|
| Python jsonschema plus existing public verifier | [Explicit registries](https://python-jsonschema.readthedocs.io/en/stable/referencing/) permit local schema resources and rejection of remote retrieval. Direct calls exercise the actual P16 implementation while independently validating the published producer structure. No schema translation or duplicate scene model is required. |
| JavaScript/Ajv plus a verifier subprocess | [Ajv schema composition](https://ajv.js.org/guide/combining-schemas.html) supports references and independently compiled validators. Credible for a JS consumer, but calling this Python public API would introduce a subprocess framing contract. That extra boundary is not needed to establish this fixture-level interaction. No relative speed claim is made. |
| CUE validation and exported fixture constraints | [CUE validation](https://cuelang.org/docs/concept/how-cue-enables-data-validation/) is credible for declarative cross-field constraints beyond this component's current languages. It would need a translated/imported producer-schema contract and still need to invoke the public signature verifier; it does not replace authentication. |

Choose portable JSON vectors with a small Python conformance consumer and explicit
no-retrieval registry. Tool installation, familiarity and rewrite cost are not reasons.
This decision is for testing the present public API; it does not select future client,
transport or real-time runtime languages. Runtime and frozen thresholds stay unchanged.

## Published boundary and retained limits

Both consumed files match fetched protected main `a7704008f0f59cbd7b4d56d3cefb5ff28bd9eb46`:
`contracts/openapi/aethron-edge-v1.json` and `contracts/fixtures/v3/unknown-output.json`.
The corpus records their exact SHA-256 hashes. Source paths in tests are fixed local
paths, not paths supplied by a network peer. No live track IDs or observations are stored.
The fixture uses the public RFC 8032 test signing key, never deployment credentials.

Three new methods initially fail on the missing corpus (three assertions, zero errors).
Six cases then cover exact UNKNOWN bytes, semantically equal reserialization, altered
state, missing evidence, task expiry and repinned policy revocation. Real successful
binding is required. Every result denies authority and qualification; rejection omits
metadata. The producer schema also rejects SAFE, an added motion-authority field and
a recommendation that does not require an independent controller.

The positive case binds evidence containing monotonic scene times 600/800 ms under a
description expiring at 1700 UTC seconds. Those domains must not be compared. The test
retains this negative fact: byte binding does not check whether an observation is current.
Its signed evidence outcome stays `unknown`, its original scene stays UNKNOWN, and no
recommendation is executed. Producer field validation cannot establish observation truth.

This is a bounded offline contract-level check, not live edge, hardware or end-to-end
sensor/runtime qualification. P2 sensor and P14 measurement contracts still require
separate consumer integration. No peer-owned files are changed. The owner workflow now
triggers on both consumed producer files so source drift prompts compatibility review.

[Local evidence](p16-edge-conformance-v3-results.json) records checks and source hashes.
Next executable task: reconcile remaining P16 existing-component review and published
sensor/runtime conformance boundaries. No lane or whole-audit completion is claimed.
