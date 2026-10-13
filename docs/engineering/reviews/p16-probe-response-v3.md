# P16 comparison response review v3

Baseline: `337a2eaa3e5997c82f43fc03468deca713eb75bd`.
Decision: **KEEP Python/Node probe; FIX evidence response validation**.
The preceding seven-file bridge commit and its source hashes were verified.
The earliest passport parser boundary was re-read and its regression suite rerun;
this supplement does not declare the entire lane audit complete.

## Constraints and technology decision

This is a local, six-vector assurance tool on a general-purpose host. It calls the
actual Python verifier and independently compares Node cryptographic primitives.
It needs typed evidence, duplicate rejection and retained negative results, without
an operational latency requirement. It is not a network admission service.

| Candidate | Decisive property and limitation |
| --- | --- |
| [Python JSON hooks](https://docs.python.org/3.13/library/json.html) | Paired-key and constant callbacks preserve duplicate detection and reject nonstandard numbers. Exact type checks are necessary: [booleans are integers](https://docs.python.org/3.13/builtins/stdtypes.html). Direct calls exercise the actual verifier without a second implementation. |
| [Node strict assertions](https://nodejs.org/api/assert.html) | Strict comparisons distinguish numeric and boolean values. Ordinary parsed JSON still needs duplicate detection before comparison; moving the driver does not eliminate that contract. |
| [Rust serde_json values](https://docs.rs/serde_json/latest/serde_json/value/enum.Value.html) | Separate Bool and Number variants make type distinctions explicit. A driver still needs duplicate-aware decoding and a binding to the actual verifier; no native deployment requirement or measured bottleneck establishes an advantage here. |
| [Java/Kotlin Jackson streaming](https://github.com/FasterXML/jackson-core/blob/2.18/src/main/java/com/fasterxml/jackson/core/StreamReadFeature.java) | Explicit strict duplicate detection offers a credible streaming alternative outside the current component languages. Typed token checks remain necessary; there is no JVM deployment constraint for this offline tool. |

KEEP is scoped to this evidence driver: exact hooks plus direct verifier calls
satisfy the contract with no additional parser dependency. This is a design
inference from the requirements and cited APIs, not a cross-language performance
ranking. No migration winner was demonstrated. No candidate was excluded because
it was uninstalled. The Jackson documentation URL failed to load; the official
source above supplied the feature evidence instead.

## Correction and retained evidence

Python list equality previously accepted `[1,1,1,1,0,1]` in place of booleans.
The tool also emitted missing/extra fields, duplicate keys, false observation flags
and invalid durations as comparison evidence. Seventeen independent response
substitutions reached the real driver and failed the new rejection test before the
fix. Only the child-process response was substituted; the Python verification and
hashing paths were real.

The driver now accepts only UTF-8 JSON of at most 4096 captured bytes, six exact
fields, six actual booleans, true parser-observation flags, a bounded Node version
label, a lowercase SHA-256 digest and a nonnegative finite binary64-range duration.
Duplicates, nonstandard constants and overflow reject. Existing comparisons still
require the expected signature outcomes and independently computed digest. Zero
and fractional durations remain valid; these are observations, not latency gates.
Malformed evidence raises before the JSON report is emitted.

[Retained results](p16-probe-response-v3-results.json) bind the reviewed sources and
normal run. All 17 new negative controls, two positive duration controls, four
optimized-mode controls and 49 passport-family test methods pass. Ruff, format,
Bandit (documented probe exclusions) and diff checks pass. No runtime protocol or
frozen bound changed.

## Limits and next review

The 4096-byte check occurs **after** `capture_output`; it does not bound child
stdout/stderr allocation or authenticate the child process. A version label is
not executable provenance. The normal run is one desktop sample, not hardware,
latency, deterministic execution or accreditation evidence. Historical results
remain historical. Insufficient information for tactical deployment.

Next: review subprocess capture resources and failure evidence. P16 transport and
cross-phase work and P17/P18 remain incomplete as recorded in the
[inventory](p16-p18-inventory-v3.md). No completion marker is created.
