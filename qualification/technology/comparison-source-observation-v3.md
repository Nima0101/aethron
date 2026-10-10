# Source observations for comparison and measurement tools

Baseline: `98915375470aff1f55da4ed47834a1e48135f2e6`. The earliest declaration,
artifact, campaign-reference and bundle APIs were reread; immutable bounded
inputs, independent negative findings and false physical-qualification flags
remain appropriate. This slice extends the [review-driver correction](source-observation-v3.md)
to `compare_ingress`, `measure_binding` and `compare_campaign`.

Each tool previously hashed source files only after its workload. A file edited
during execution could receive the reported digest without a mismatch being
detected. Ingress export made no source observation at all. Historical records
remain unchanged; they identify observed file contents, not authenticated execution.

Each entry point now captures its fixed inventory before fixture construction,
semantic collection or contract execution. Before emitting JSON it verifies a
second observation and retains the initial digests. Ingress export performs the
same check before emitting its unchanged hex-line transport. Missing initial
sources prevent workload admission; missing final sources or changed digests
prevent all output. Fixed errors are `review_sources_unavailable` and
`review_sources_changed`. All three reports add `source_observation` with value
`equal_before_and_after_workload` and include the shared helper in their inventory.

Source checks remain outside timed and traced workload calls. Existing trace
ownership, response limits, report/document parity, candidate-call checks and
duplicate-mutation evidence remain in force. Export still does no measurement.
Production admission contracts and frozen thresholds are unchanged.

## Technology reassessment

Requirements are fixed trusted checkout inputs, Python 3.9/3.13 workload drivers,
raw-byte SHA-256 observations, direct access to workload start/end, and unchanged
transport and measurement semantics. There is no native ABI, untrusted-path
service, build sandbox, hard deadline or new distribution requirement.

| Candidate | Decisive fit and limitation |
|---|---|
| Python orchestration with native hashing | Directly brackets the existing workload and preserves byte digests without a process handshake. It requires explicit source comparisons; a digest alone is insufficient. |
| Git tree/object inventory | Useful immutable publication identity. It does not establish equality with loaded Python code or the working files observed during a run. |
| Nix derivation/build orchestration | Credible when the requirement is controlled build inputs and execution. It defines a different execution protocol from this source-checkout workload; file observations must not be relabeled as a Nix-style build result. |
| F# or C#/.NET hashing coordinator | Supports hashing bytes and streams. A separate coordinator would need a lifecycle handshake with the Python workload; no required independent-service or native-ABI property selects that extra boundary here. |

**KEEP Python orchestration; FIX source consistency.** The choice follows direct
control of the actual workload boundary, not installation, familiarity or rewrite
cost. It introduces no runtime-speed ranking. Reopen for a hermetic build,
independent execution attestation or measured target-resource requirement.

Official mechanism sources rechecked:
[Python hashing](https://docs.python.org/3.13/library/hashlib.html),
[Git tree inventory](https://git-scm.com/docs/git-ls-tree),
[Nix derivations](https://nix.dev/manual/nix/2.34/language/derivations.html), and
[.NET byte/stream hashing](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.sha256.hashdata?view=net-9.0).
The component suitability decision is the analysis above, not a vendor claim.

## Evidence and limits

Four regression methods cover all three report modes and ingress export. Real
workload functions run while the source reader injects a changed/missing file
observation. The RED run has 15 assertion failures, zero execution errors: twelve
failure-boundary cases and three missing-metadata controls. Stable export already
matched its expected transport. After correction, 22 related methods pass,
including existing response-admission, tracing-lifecycle and comparison-result
controls. Ruff check/format, targeted Bandit and Python 3.9 syntax parsing pass.
Syntax parsing is not local Python 3.9 execution.

Fresh subprocess reports and export agreement are recorded in
[the source-bound result](comparison-source-observation-v3.json). Ingress responses
are explicitly synthetic Python fixtures; no Java execution is established by
this run. SQL shares admission and capture semantics with the Python oracle.
All timings are descriptive shared-host samples, not qualification thresholds.

The helper reads fixed trusted source files as whole byte strings. These checks
add no file-size or time bound. Before/after observations are non-atomic and do
not detect transient reverted edits, stale imports, changed import resolution,
unlisted dependencies, malicious instrumentation or post-check changes. The Java
source digest does not authenticate a compiled parser or response producer.
No runtime, supply-chain, physical or customer-acceptance attestation follows.
Use a fresh process in a controlled checkout. Complete lane review and P15/P19
producer integration remain open; no audit-complete marker is justified here.
