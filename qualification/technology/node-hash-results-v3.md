# Node hash measurement results — review v3

Baseline: `21f1b7525566dde470c4070a4efb2185bdbf9180`. The continuation
verified the preceding bridge and source observations, reran earliest declaration,
artifact and campaign controls, and reviewed the Node hash probe and its hosted
invocation. Nineteen baseline methods passed. The probe only retained the last
iteration's hashes: an earlier incorrect result could disappear from its output.
Known-vector and ownership failures also did not prevent successful process exit.
Hosted checks examined final values but could not recover discarded intermediate
results. This is an audit-evidence defect, not an observed hash-library defect.

## Constraints and technology choice

The experiment specifically observes Node Buffer copy/alias behavior and its
synchronous native hash API over ten repetitions of four 1 MiB inputs. Inputs are
synthetic and fixed. It is an offline source-checkout experiment with no service,
device, secret, network or hardware timing requirement. Every measured result must
be checked without adding that check to the copy-and-hash interval.

| Candidate | Decisive property |
|---|---|
| Node JavaScript, Buffer and crypto | Directly observes the selected runtime's mutable byte ownership and synchronous hash workload. Fixed literal expectations can be checked immediately after each timed call. |
| F#/C# with SHA256.HashData | Credible byte/stream hashing and an independent comparison host. Replacing the subject would measure .NET allocation and ownership rather than Node Buffer behavior. An external check of only the final JSON cannot recover discarded results. |
| Erlang/OTP crypto with binary data | Credible native hashing ecosystem. Its binary representation is a different ownership experiment; it does not answer this Node alias/copy question. Consider separately if a BEAM consumer becomes required. |

**KEEP JavaScript for the Node experiment; FIX all-result admission.** This is a
choice of experimental subject, not incumbent preference or a claim that Node is
the best production validator. Production qualification admission stays separate.
No alternate-runtime performance ranking follows. Sources inspected 2026-10-10:
[Node crypto](https://nodejs.org/docs/latest-v22.x/api/crypto.html),
[Node Buffer](https://nodejs.org/api/buffer.html),
[.NET SHA256](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.sha256.hashdata?view=net-9.0),
and [Erlang crypto](https://www.erlang.org/doc/apps/crypto/crypto.html#hash/2).
The version-specific Buffer URL failed; the general official page was available.
Local behavior was tested on Node 22.23.2, not inferred from the latest documentation.
The suitability assessment is this review's analysis.

## Correction and evidence

Four literal hashes of the fixed 1 MiB buffers were independently checked with
Python hashlib. Each loop compares all four returned digest strings against those
expectations after stopping its timer. The empty/abc vector hashes must match
their literal expected values. Both ownership outcomes must be true before JSON
output; preservation compares to the literal abc hash. Any of these failures
throws `hash_probe_result_failed`. Source observations still bracket the workload.
Report metadata identifies all-result checking and its exclusion from timings.

Three new methods run actual bounded Node subprocesses against disposable copies.
Fault hooks replace each of forty measured digest positions individually, the two
known-vector results, and the copy/alias behaviors. Each requires an injection
marker, unchanged probe-file bytes, nonzero exit, no report JSON and the intended
error. Before correction all 44 variants escaped rejection: 44 assertion failures,
zero execution errors. After correction all nine Node integration methods pass,
including existing source mutation controls and four known ingress duplicate-key
mismatches. The normal hash results remain compatible with the earlier evidence.

Node syntax, Python lint and formatting checks pass. Bandit findings on the test
launcher are retained: subprocess import, invocation and PATH lookup. Commands
use fixed Node/driver names, no shell, disposable local scripts, one worker-pool
setting and a 15-second timeout. These controls do not inspect secrets or run
remote code. This is not a claim that Bandit scans JavaScript.

The existing hosted workflow explicitly invokes `qualification.tests.node_provenance`,
so these methods need no new workflow step. Configuration is not evidence of a
hosted run for this correction. Historical results remain unchanged; neither
ten samples nor the finite fault controls establish sustained performance,
cryptographic certification, authenticated execution or physical qualification.
The full lane re-audit remains incomplete; hosted configuration and P15/P19
acceptance work remain. Insufficient information for tactical deployment.
