# Portable synthetic consumer vectors v1

[fixtures/consumer-vectors-v1.json](fixtures/consumer-vectors-v1.json) provides
language-independent inputs and expected checks for the existing offline bundle
and artifact APIs. It supplies no physical observations, authorization decisions,
weapon interfaces or hardware qualification. It is a tracked test fixture, not
a new production admission protocol or an acceptance certificate.

The root has exactly `version` (integer 1), `plan_utf8`, `manifests_utf8` and
`cases`. Encode the decoded `plan_utf8` string directly as UTF-8. For each capture,
look up `manifest_key` in `manifests_utf8` and encode that decoded string directly
as UTF-8. Do not parse and reserialize these embedded JSON strings: their exact
whitespace participates in byte commitments. The complete manifest deliberately
ends in a space and LF. Do not append any other bytes.

Each case contains exactly `id`, `captures`, `domain_hex`, `procedure_hex`,
`artifacts_hex` and `expected`. Each capture has `case_id`, `manifest_key` and
`now_ms`. Decode hexadecimal strings to bytes, without text interpretation.
`artifacts_hex` maps declared SHA-256 keys to supplied artifact bytes. Preserve
all capture occurrences and their instants. Pass the raw plan/captures/reference
bytes to the [bundle API](campaign-bundle-v1.md); separately pass each original
manifest, its instant and the artifact mapping to the [artifact API](artifacts-v1.md).

`expected.bundle` provides `coverage_findings`, `reference_findings`,
`software_checks_passed` and `capture_counts`. `expected.artifacts` is an array
in capture order, each containing `declaration_findings`, `artifact_findings`,
`software_checks_passed` and `artifact_bytes_verified`. Compare those projections
exactly, including boolean types. Independently require all bundle authenticity,
domain, procedure, artifact-verification and physical flags to remain false;
artifact authenticity and physical qualification must also remain false.
This is partial report conformance, not an oracle for every output field.

All six case IDs must occur exactly once:

| Case | Expected distinction |
|---|---|
| `complete` | Both software checks pass; no authenticity or physical approval. |
| `stale` | Matching bytes cannot remove stale-capture and missing-coverage findings. |
| `altered_artifact` | A passing bundle cannot approve changed artifact bytes. |
| `wrong_references` | Matching capture artifacts cannot approve either wrong reference. |
| `expired_and_altered` | Calibration expiry and altered artifacts retain independent failures. |
| `reused_capture` | Both occurrences pass artifact checks but campaign coverage rejects reuse. |

The source-checkout runner imports no Python fixture builders and performs six
bundle evaluations and seven artifact evaluations. It bounds fixture reads to
32,769 bytes and rejects sizes above 32,768 before JSON parsing. Each test requires
the exact non-empty case inventory and one expected artifact result per capture,
so an empty or shortened corpus cannot silently pass. This is a trusted,
repository-owned fixture loader, not a hardened parser for arbitrary test uploads.
Malformed fixtures fail the test; the loader does not promise fixed private errors.

```sh
python3 -m unittest qualification.tests.test_consumer_vectors -v
```

Expected findings were authored from the v1 contracts, not copied from validator
responses. Input documents reuse the existing synthetic rig construction and
contain no hardware evidence. The three methods first failed because the corpus
was absent, then passed with all six cases. This RED concerns missing portable
evidence, not a production-validator defect. Mutation controls on temporary copies
also reject empty, missing and duplicate cases, erased stale findings and altered
bytes misreported as passing. Existing CI discovery includes these tests; no
hosted or independent cross-language consumer execution is claimed.

## Technology selection — 2026-10-10

Requirements are small offline reviewable vectors, exact manifest-byte replay,
portable integer/boolean expectations and no executable fixture language. The
representation must be consumable without the current language's fixture helpers.

| Candidate | Decisive property for this corpus |
|---|---|
| JSON with embedded UTF-8 strings and hexadecimal payloads | Explicit portable values and reviewable text; direct UTF-8 encoding preserves the selected manifest bytes. Hexadecimal has a size cost, acceptable for these tiny opaque payloads. |
| CBOR | Native byte strings and compact encoding are credible for a larger binary corpus. No storage/bandwidth requirement here outweighs direct textual review. |
| YAML 1.2 | Human-readable mappings and richer scalar forms. Byte-sensitive embedded documents would require careful scalar/chomping rules; that flexibility is unnecessary for these fixed vectors. |
| CUE plus exported JSON | Useful constraints and data validation for a generated matrix. The current finite corpus needs no constraint evaluation or generation at consumption time. |

**SELECT JSON fixture data; KEEP the direct Python reference runner.** JSON is the
interoperability artifact; Python only exercises the existing typed APIs. A native
or .NET/BEAM runner can consume the vectors when such an implementation is published.
The [runner comparison](technology/bundle-artifact-integration-v3.md) explains
direct tests versus Robot Framework, F#/NUnit and Erlang Common Test. This decision
is based on byte fidelity and reviewability, not incumbent preference. There is
no runtime performance comparison or full-schema interoperability claim.

Sources consulted: [JSON](https://www.rfc-editor.org/rfc/rfc8259),
[CBOR](https://www.rfc-editor.org/rfc/rfc8949),
[YAML 1.2.2](https://yaml.org/spec/1.2.2/), and
[CUE validation](https://cuelang.org/docs/concept/how-cue-enables-data-validation/).
The suitability judgment is this review's analysis. Recorded results and source
observations are in [consumer-vectors-review-v3.json](technology/consumer-vectors-review-v3.json).
