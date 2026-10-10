# P4/P15 implemented-source review checkpoint

Reviewed baseline: `52cd6f093d7940194e9bdd4725fe6016bd153d68`, starting from
`eebfad4`'s declaration boundary. The review covers the 21 tracked implementation
and experiment source files under `qualification/`, plus the owned workflow.
The [JSON inventory](coverage-review-v3.json) enumerates those files, current
fingerprints, component decisions and source-matching historical records.
Historical records are evidence inputs, not fresh execution results. Matching
source bytes is not execution attestation or complete dependency closure.

The implemented-component review has caught up to this baseline. **The lane and
P15/P19 software delivery remain incomplete.** This checkpoint does not freeze
future technology choices or create an audit-completion marker for unfinished
phase deliverables. Missing native-device, installed-product and help validators
cannot be classified as completed merely because physical evidence is external.

## Fresh decisions against actual deployment

All current production entry points are synchronous offline source-checkout APIs
or supervised stdin commands. They access no device, network, persistent store,
actuator or authorization service. Exact integer types, immutable bytes, fixed
errors, preserved negative findings and explicit input budgets are decisive.
There is no established target ABI, scheduler deadline, RSS ceiling or sustained
throughput requirement. Read and flush deadlines belong to the invoking process.
Do not infer deterministic target latency from finite shared-host experiments.

| Component | Reassessed alternatives and decisive requirement | Current decision |
|---|---|---|
| Declaration schema and findings | CUE/Pydantic constraints, C# streaming JSON and Rust visitors are credible. Each still needs explicit duplicate/token rules, cross-record findings and byte commitments. The configured Python hooks and bounded integer checks expose these rules directly and pass the current negative corpus. | KEEP Python bounded decoder and semantic checks. No schema framework alone replaces evidence provenance. |
| Artifact and opaque reference binding | Erlang/Elixir immutable binaries, Rust owned buffers, C# memory views and Node owned buffers were reconsidered. Read-only views do not alone establish immutable backing storage. The current exact Python bytes boundary composes native hashing without a payload conversion. | KEEP immutable byte APIs/native hashing. Matching content never establishes authorization or reference semantics. |
| Campaign coverage | SQLite relational aggregation, Rego and Souffle suit relational/policy workloads. Here at most 64 submissions require multiset preservation and ordered commitments, with no persistence or distributed policy requirement. The SQL candidate independently checks aggregation while sharing admission and declaration semantics. | KEEP direct aggregation; retain SQL comparison and duplicate counterexamples. |
| Bundle composition | Rego/CUE hosts and native typed orchestration remain credible. The present requirement is executing two existing raw-byte contracts against exactly one immutable plan, retaining both failure groups. | KEEP direct composition; no precomputed approval input. |
| CLI and fixed binary frame | Go binary decoding, Rust byte decoding, Erlang bit syntax and CBOR are viable transport ecosystems. The current fixed fields need exact bytes, pre-read length checks and direct validator transfer, not a generic interchange parser or service supervision. | KEEP Python bounded framing and explicit process exit handling. Supervision and partial-output limits remain documented. |
| Review and measurement orchestration | pytest, Node's test runner and JVM/.NET runners offer alternate test engines; native/RSS profilers measure other quantities. The current tools require direct mutation/result access to these Python APIs and explicitly named Python allocation observations. | KEEP orchestration and tracing with result checks/session ownership. No RSS or statistical-performance claim. |
| Java and Node experiments | Candidate runtimes are experimental subjects: Java/Jackson token admission and Node JSON/Buffer/native hash behavior. Porting a subject's probe would stop measuring that subject. | KEEP experimental implementations only. Java still uses the Python semantic oracle; Node ingress retains four negative cases. |
| Hosted verification | F# process coordination, Python subprocesses and Nix build graphs cannot replace the host's cancellation and step-outcome policy. | KEEP native Actions scheduling with the corrected preparation/failure conditions. |

These are requirement-specific engineering decisions, not a universal language
ranking, an installation constraint or an argument based on rewrite cost.
Native ABI requirements, measured resource deficits, independently distributed
policies, durable acquisition ledgers or installed distribution boundaries reopen
selection before their implementation. No locally demonstrated winning migration
is left deferred for the implemented components at this checkpoint.

The component-specific broad comparisons and finite experiments are in
[the main review](review-v3.md), [reference binding](../campaign-references-v1.md),
[bundle composition](../campaign-bundle-v1.md), [framing](../campaign-bundle-stream-v1.md)
and [workflow scheduling](workflow-failure-review-v3.md).
Primary ecosystem documentation rechecked for this checkpoint:
[Python JSON hooks and limits](https://docs.python.org/3.13/library/json.html),
[CUE validation](https://cuelang.org/docs/concept/how-cue-enables-data-validation/),
[C# streaming JSON](https://learn.microsoft.com/en-us/dotnet/standard/serialization/system-text-json/use-utf8jsonreader),
[Erlang binary framing](https://www.erlang.org/doc/system/bit_syntax.html),
[Erlang crypto](https://www.erlang.org/doc/apps/crypto/crypto.html#hash/2),
[Rego](https://www.openpolicyagent.org/docs/policy-language), and
[SQLite SELECT](https://www.sqlite.org/lang_select.html).
These sources describe mechanisms; they do not certify this implementation.

## Corrections, verification and limits

The README incorrectly grouped missing power/weather/temperature/vibration/EMC
software checks with external evidence gates. It now identifies them as
unimplemented software, separately from real measurements and independent review.
The [readiness inventory](../p15-readiness-v1.md) already makes that distinction.
No wire contract, frozen threshold or production code changed in this checkpoint.

Fresh focused execution passed 73 production/consumer tests and 37 audit-tool
methods. A locally compiled pinned-Jackson probe passed eight transport tests and
all 81 request comparisons, including document fidelity. This local runtime is
JDK 21, not the configured hosted JDK 17. The fresh Node ingress report remains
`parity: false` for `duplicate-equal`, `duplicate-overwrite`, `duplicate-escaped`
and `nested-duplicate`. Those failures are retained in the checkpoint JSON; they
prevent treating that primitive as a substitute for production admission.

Twenty implementation source files have matching fingerprints in older retained
records. The current Node ingress source lacked such a match; its freshly executed
report supplies the current observation and retains the four mismatches. That is
an evidence-coverage correction, not a new claim that source hashes authenticate
execution. Raw Java request/response files and execution outputs are retained in
the lane runtime; their hashes and comparison results accompany this checkpoint.

The main fetch failed with read-only `FETCH_HEAD`. Cached main
`fce89d3904ddbfb004b55718fab955c91a9c49a0` is not represented as a fresh remote
snapshot. No peer implementation or unpublished interface is imported here.
No physical, cryptographic-certification, MLS/ZTA-enforcement, five-nines or
customer-acceptance claim follows. Insufficient information for tactical deployment.

Next executable software work is the versioned non-executing procedure-content
contract identified in the readiness inventory, with its own technology decision,
strict admission and negative fixtures. Opaque reference matching remains v1 and
must not be silently redefined as semantic validation or human approval.
