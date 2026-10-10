# P16 structural conformance review v3

Baseline: `2519b63ff4383f2c6a2d4820370cb6581b42b885`. Reviewed 2026-10-10.
Decision: **KEEP JSON Schema 2020-12 and python-jsonschema; FIX vacuous runtime
comparison and its hosted dependency closure; CLARIFY coverage and selection rationale**.
No production verifier, schema acceptance set or signed fixture changed.

## Requirements and candidate reassessment

Consumers need portable closed structural contracts for three passport documents.
Offline tests must validate trusted local schemas, reject remote retrieval, check bounded
negative fixtures and separate shape acceptance from signature/policy acceptance. This
is development/CI tooling with no physical target, service throughput SLA or real-time
deadline. Schema validation cannot recover duplicate JSON keys or original float lexemes,
authenticate a signature, persist trust floors or confer authority.

| Candidate | Decisive properties |
|---|---|
| JSON Schema / python-jsonschema | [Referencing registry](https://python-jsonschema.readthedocs.io/en/stable/referencing/) supports explicit retrieval control and installed resources. The current suite independently tests closed shapes, mathematical integer semantics and denial of external references. Runtime comparisons can call the verifier directly. |
| JSON Schema / JavaScript Ajv | [Security guidance](https://ajv.js.org/security.html) documents trusted-schema assumptions, generated validation and resource/regex concerns. Native ECMAScript regex behavior is attractive for portability checks. Compilation speed is not a deciding requirement for this small fixed corpus; full authentication still needs a separate verifier. |
| CUE constraints | [CUE's configuration model](https://cuelang.org/docs/concept/how-cue-enables-configuration/) uses constraints and unification and is credible for authoring consistent configuration. Using it here would require validating the exported JSON Schema against the same consumer contract; it does not replace lexical or signature checks. |
| Rust jsonschema | [Native validator](https://docs.rs/jsonschema/latest/jsonschema/) provides validation and configurable resource retrieval. A credible choice for a native consumer or measured larger corpus, with retrieval disabled explicitly. Native execution alone does not establish stronger conformance evidence. |

KEEP the portable schema format and current checker: explicit registry isolation and
direct positive/negative verifier comparisons fit the offline corpus without custom
validation code. The reviewed alternatives are viable; no measured or requirement-derived
benefit currently establishes a winning migration. Installed tools, language familiarity
or avoiding a compiler are not reasons for this decision. This is not a claim that Python
is fastest or that the checker proves interoperability with every schema implementation.

## Observed failure and correction

The old runtime comparison asserted only that three structurally valid policies were
rejected. Replacing the verifier with a stub that always returned `crypto_unavailable`
still passed that test, with no skips. Thus the comparison did not establish that its
environment could authenticate even a valid signature. The schema-only job installed
the schema tool but not the optional crypto closure.

A new regression expects that always-rejecting stub to be detected. It first failed
with `AssertionError not raised`. The comparison now authenticates a known-good signed
fixture before the negative cases and checks their specific reasons: expired policy,
revoked statement and invalid key-ID binding. The conformance requirements include the
existing pinned passport closure, and the hosted job imports both tools explicitly.
The corrected regression and all seven conformance tests pass locally.

This is a verification-evidence defect, not a demonstrated production acceptance flaw.
Structural-only checks remain distinct from signature verification. Documentation now
names the two covered passport fixture families; it does not imply this test covers all
later task/federation/inbox vectors. Those have separate focused tests.

Reviewed supporting tooling: the existing Python/Node primitive probe labels itself a
V2 sample and not a full verifier benchmark. It is supporting evidence only. The trust
mutation probe modifies isolated modules in memory and checks fixed source substitutions;
it is test tooling, never an untrusted-input execution path or qualification result.
Neither probe establishes physical latency, MLS, CNSA or deployed availability.

Reproduce with the pinned optional conformance environment:

```sh
python -m unittest discover -s tests -p test_passport_schemas.py -v
python -m unittest discover -s tests -p 'test_passport*.py'
python -m unittest discover -s tests -p 'test_interop*.py'
```

Source hashes and bounded results are in [the evidence record](p16-conformance-v3-results.json).
Hosted execution of this correction is still pending; workflow edits are not a hosted
PASS. Next earliest component: P16 task descriptions. V3 remains incomplete.
