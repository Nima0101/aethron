# Portable assessment review vectors v1

[The corpus](fixtures/assessment-vectors-v1.json) contains ten synthetic raw-input
cases for the existing [assessment API](assessment-v1.md). It changes no production
gate, threshold or wire contract. Its purpose is executable review evidence that
does not require Python fixture builders. Other-language, installed-release and
physical acceptance remain unverified.

Root fields are exactly `version` (integer 1) and `cases`. Each case has `id`,
`plan_hex`, `domain_hex`, `procedure_hex`, `methods_hex`, `captures`,
`expected_report` and `expected_error`. Decode lowercase hex to bytes directly;
do not parse and reserialize embedded JSON. Invalid UTF-8 and duplicate JSON keys
are deliberate test data. Preserve trailing whitespace and every capture occurrence.

`methods_hex` maps claimed digests to method bytes. Each capture has `case_id`,
`manifest_hex`, `now_ms` and `artifacts_hex`; the latter maps claimed digests to
artifact bytes. Pass these inputs to `assessment.evaluate` in the documented order.
The invalid-instant case deliberately uses a Boolean; consumers must preserve
that type and reject it rather than coercing it to an integer.

For the eight admitted cases, compare every field of `expected_report`, including
nested types, list order and absence of extra fields. For the two malformed cases,
require `invalid_qualification_assessment` and no report. JSON object key order
does not matter. Every physical/authentication flag remains false even in the
software-only success case.

| Case | Required distinction |
|---|---|
| complete | All software gates pass; no physical approval. |
| stale | Matching artifacts cannot erase stale-capture findings. |
| domain_unknown | Unknown domain lighting is not a wildcard. |
| method_unknown | Matching method bytes cannot resolve an unknown rule. |
| artifact_missing | Complete declarations cannot replace absent bytes. |
| simultaneous | Coverage, domain, method and artifact failures all remain. |
| reused | Individually valid artifact results cannot approve capture reuse. |
| malformed_capture | Invalid UTF-8 becomes a retained failed capture. |
| invalid_plan | Duplicate root version keys cause fixed-error rejection. |
| invalid_instant | Boolean evaluation instants cause fixed-error rejection. |

The [reference runner](tests/test_assessment_vectors.py) reads at most 262145 bytes,
rejects a corpus larger than 262144, and requires SHA-256
`afe52af644bbc67dc0bdb0df3d13839ab1a3c3d768471ce32b02d314d899fa2c`
before JSON decoding. It also requires all ten distinct names, asserts their
negative meanings independently and rejects Boolean/float substitutions in nested
integer results. The fixture is 133639 bytes; this is fixture size, not runtime
memory or performance evidence. It is a repository-owned fixture reader, not an
upload admission endpoint. The hash detects changed fixture bytes, not malicious
changes to both the fixture and trusted runner.

Expected full reports were initially obtained from the reference implementation
at `0c2c58e273378f24a83ae56abf274257f553ba25`, then reviewed against the named
outcomes and existing independent gate tests. They are regression expectations,
not an independent proof of every computed field. Tests never regenerate or
overwrite them. A changed expectation requires explicit review and a new pin.

The [technology decision](technology/assessment-vectors-decision-v1.json) compares
JSON+hex with [CBOR byte strings](https://www.rfc-editor.org/rfc/rfc8949.html) and
[Protocol Buffers](https://protobuf.dev/programming-guides/encoding/).
[JSON](https://www.rfc-editor.org/rfc/rfc8259.html) plus hex is selected for this
small inspectable fixture; no constrained transport benchmark is claimed. Python
is the reference runner only, directly calling the current API. No second language
is required to read the corpus; successful interoperability still needs an actual
consumer execution. Existing [C4 views](assessment-v1.md#c4-views) apply unchanged.

## Review boundary

The current review restarted with declaration byte/type admission and rig/time
findings, then checked artifact/reference binding and assessment composition.
Their non-qualification semantics remain correct for the documented offline
source-checkout scope. The corrected gap is evidence portability, not hardware
behavior. Historical diagnostic comparisons remain evidence inputs; this slice
does not claim a fresh review of every diagnostic tool or completion of P15/P19.

Run `python3 -m unittest qualification.tests.test_assessment_vectors -q` from the
checkout. Hosted discovery already includes this test file; workflow existence is
not a hosted PASS. No physical observations, authorization decisions, release
attestation or certification follow. Insufficient information for tactical deployment.
