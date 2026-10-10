# P5 simulation-only defensive interface — focused evidence

Date: 2026-10-10. Python 3.13.5, Linux x86_64. Software admission evidence only;
no verified sensing, physical controller, actuator, field safety or certification.

## Retained counterexamples and tests

Initial RED: importing `aethron.simulated_safety` failed before implementation.
Portable-vector RED: `contracts/fixtures/simulation/defensive-v1.json` was absent
before the schema/vector export was added.

Expiry RED: a declaration at 0ms requested expiry at 200ms and was read at 50ms.
`test_declared_expiry_cannot_extend_current_support_age` failed with
`AssertionError: 200 != 100`. The returned PRESENT deadline is now capped at
input time +100ms. The failure remains a regression test; no frozen v3 limit changed.

`python3 -m unittest discover -s tests -p test_simulated_safety.py -v` passes all
nine tests, including six portable vectors. Coverage includes all five defensive
contracts, immutable motion-authority denial, UNKNOWN semantics, input clock and
frame high-water marks, exclusive expiry/age boundaries, unsupported evidence,
unknown/private fields, duplicate/oversized/deep bytes, booleans/nonfinite times,
watchdog evidence withdrawal, permanent close and detached diagnostic arrays.

Ruff 0.16.10 check/format and Bandit 1.9.4 PASS on the new module and test/tool files.
Independent schema validation with jsonschema 4.25.1 passes the Draft 2020-12
metaschema, all six response vectors and 30 negative mutations (motion authority,
simulation mode, action, unknown identity field and boolean timestamp). This
validator is a local development tool, not a runtime dependency.
Full fuzzing, packaging/clean-clone, full repository and physical qualification
remain outside this lane's local fast-loop scope. Hosted gates remain required.

## Bounded resource diagnostic

The [retained sample](simulated-defensive-resource-v1.json) includes the source
hash and all 100 wall samples. On 100 aggregate synthetic declarations, measured
p50 was 0.0240ms, p95 0.1097ms and maximum 0.2259ms; a separate traced pass peaked
at 3417 bytes. This is a small software diagnostic, not a worst-case bound or a
comparison against another language. It supports the current deployment decision
in the [contract](../architecture/simulated-defensive-v1.md), alongside the
[policy-v2 technology audit](../decisions/0008-world-technology-reassessment-v2.md).

P8 consumers should use the versioned schema and vectors only after their merged
publication. An admitted synthetic declaration authenticates neither a sensor
nor a caller, and never grants motion authority.
