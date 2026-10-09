# Retrospective technology audit, policy 2 — in progress

This audit covers the existing qualification software in historical order:
declaration validation (including rig, calibration, clock and environment
rules), artifact byte binding, campaign coverage, then CLI/report delivery and
verification tooling. None has a completed policy-2 KEEP/MIGRATE decision yet.
Earlier technology notes are hypotheses to reassess, not completion evidence.
No new qualification capability or physical result is claimed by this audit.

## Declaration validator: operational constraints

This is an offline source-checkout library and stdin CLI. Its untrusted UTF-8
input is bounded to 65,536 bytes, depth 8, five sensors and fifteen records.
Duplicate keys must be rejected after escape decoding. Integers, decimal and
exponent tokens cannot silently interchange; timestamps have an exact bounded
integer domain. Exact input bytes and canonical rig bytes have separate hash
commitments. Fixed errors must not echo input. Negative calibration, timing,
binding and missing-evidence findings must survive report generation.

The deployment has no device SDK, actuator interface or hard real-time deadline.
The frozen 100 ms freshness gate describes evidence age, not permissible CLI
processing latency. Runtime startup, bounded allocation, portability and ongoing
dependency maintenance matter; no language receives preference because it is
installed. Both syntax admission and semantic findings require migration parity.

## Candidate discovery and decisive properties

| Candidate | Supporting property | Remaining obligation |
|---|---|---|
| Python standard library | Pair and numeric-token hooks preserve the distinctions needed at ingress. | Defaults are permissive; independently verify custom bounds, exact types, and full rule behavior. |
| CUE | Closed definitions and relational constraints can express schema and field relationships. | Check duplicate-field unification and numeric lexical behavior before treating it as the raw evidence boundary; hash/report orchestration also needs evaluation. |
| TypeScript with Ajv | Compiled closed-shape and conditional validation; source-aware JSON revivers can examine number spelling. | Revivers still lose duplicate members in the measured configuration; an additional tokenizer would need assessment. |
| C# System.Text.Json | UTF-8 span reader permits low-allocation token admission with static types. | Prototype duplicate tracking, numeric token inspection, byte/depth bounds and fixed error conversion. |
| Java/Jackson | Streaming constraints and explicit duplicate detection are available. | Check exact byte caps outside library document-length constraints, token typing and deployment resource behavior. |
| Rust/Serde | Typed numeric representations and custom visitors support strict decoding. | Test duplicate handling in the chosen deserializer, bounded arithmetic and the complete finding/report contract. |
| Go encoding/json | Token iteration and number-token preservation are available. | Default object decoding is insufficient; evaluate configured duplicate, UTF-8, lexical number and schema admission. |

Primary sources inspected 2026-10-10:

- [Python JSON hooks, defaults and limits](https://docs.python.org/3.13/library/json.html).
- [CUE validation](https://cuelang.org/docs/concept/how-cue-enables-data-validation/)
  and [language semantics](https://cuelang.org/docs/reference/spec/).
- [Ajv schema support](https://ajv.js.org/json-schema.html) and
  [ECMAScript JSON parsing](https://tc39.es/ecma262/multipage/structured-data.html#sec-json.parse).
- [System.Text.Json UTF-8 reader](https://learn.microsoft.com/en-us/dotnet/standard/serialization/system-text-json/use-utf8jsonreader).
- [Jackson streaming constraints source](https://github.com/FasterXML/jackson-core/blob/3.x/src/main/java/tools/jackson/core/StreamReadConstraints.java),
  [duplicate detection](https://fasterxml.github.io/jackson-core/javadoc/2.14/com/fasterxml/jackson/core/StreamReadFeature.html)
  and [document-length advisory](https://github.com/FasterXML/jackson-core/security/advisories/GHSA-2m67-wjpj-xhg9).
- [Serde JSON number representation](https://docs.rs/serde_json/latest/serde_json/struct.Number.html).
- [Go JSON package](https://pkg.go.dev/encoding/json).

## Executable ingress evidence

`ingress-vectors-v1.json` contains eighteen exact-byte synthetic cases, encoded
as hexadecimal for reuse across languages. Expected rejection and findings are
literal contract expectations. Accepted incomplete declarations retain all three
missing-evidence findings; acceptance is not a qualification pass.

```sh
python3 -m unittest qualification.tests.test_ingress_audit -v
node --v8-pool-size=1 qualification/technology/ingress-probe.mjs
```

The test initially failed because the portable corpus was absent. With the corpus,
the production validator matches all eighteen expectations on Python 3.13.5.
Removing duplicate detection, accepting integral floats or decoding malformed
UTF-8 permissively would break these cases.

The Node 22.23.2 prototype uses fatal UTF-8 decoding, retains the BOM for rejection,
checks a source-aware numeric reviver, and limits byte length and integer tokens.
It matches fourteen cases but accepts four prohibited duplicate-member cases:
equal values, overwritten values, escaped names, and nested duplicates. The
negative result is retained in `ingress-node-result-v1.json`. Modern revivers do
preserve numeric source spelling here; dismissing JavaScript solely for losing
integer-versus-decimal spelling would be incorrect.

The probe is deliberately **not** a full alternative validator: it has no schema,
depth gate, timing rules or reports. It is not imported by production software,
and its successful process exit does not mean parity. This evidence rules out
this parser configuration as a drop-in replacement; it does not rule out other
JavaScript parsers, and does not establish Python as the overall winner.

Local sandbox process/namespace allocation failed during the audit and later
recovered intermittently. No latency comparison is credible from this run.
Two initial Jackson documentation requests failed; the sources above were
located subsequently. These limitations remain part of the audit record.

## Cursor and next experiment

Cursor: declaration validation, decision pending. Next compare a strict streaming
candidate (System.Text.Json or Jackson) against the same ingress corpus and
semantic report fixtures, then assess bounded startup/allocation measurements
under a stable runner. Complete KEEP/MIGRATE evidence and any winning migration
before advancing to artifact binding. No audit completion marker is warranted.
