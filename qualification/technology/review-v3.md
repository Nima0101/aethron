# Qualification implementation review v3 — in progress

This is an implementation review record, not a replacement governance policy.
The review starts at the earliest declaration component in commit `eebfad47`
and covers the lane built through `a5158617`. Earlier decisions are evidence
inputs only. No audit-complete marker or physical qualification is asserted.

| Historical component | Current review state |
|---|---|
| Rig, calibration, clock, environment declaration validator | KEEP implementation; FIX evidence coverage; CLARIFY claims |
| Artifact byte binding | KEEP implementation; FIX evidence coverage; CLARIFY report lifetime |
| P15 campaign coverage and procedures | Pending fresh review |
| CLI/report delivery and verification tooling, including audit probes | Pending fresh review |

## Declaration deployment and technology decision

The actual deployed boundary is a source-checkout, synchronous offline byte API:
65,536 bytes, depth eight, five sensors and fifteen records. It returns fixed
findings and aggregate metadata. It has no device SDK, DDS loop, actuator,
authorization service or persistent state. Exact token types, duplicate rejection,
bounded integer arithmetic, negative evidence retention and private error handling
take priority. A hard deadline, target OS scheduling contract, memory ceiling or
standalone native distribution requirement has not been established. No local
benchmark establishes physical real-time performance.

The fresh comparison retains the prior broad candidate discovery and adds
schema-oriented options rather than restricting the search to repository languages:

| Candidate | Current decisive properties |
|---|---|
| Python JSON hooks and explicit semantic checks | Immutable byte input, pair hooks, exact integer checks and fixed exceptions directly implement the present contract. Permissive defaults still require the existing guards. |
| Pydantic strict models | Useful typed admission and field constraints. Strictness must be configured and differs between JSON and Python representations; a model alone does not demonstrate duplicate-key or byte-commitment parity. |
| CUE closed constraints | Expresses required fields, numeric limits and relationships. Raw token distinctions, duplicate rejection and fixed error/report commitments still need a checked boundary. |
| C# System.Text.Json | Forward-only UTF-8 token inspection is a credible allocation-conscious alternative. Application code must implement duplicate tracking, exact types and cross-record findings. |
| Java/Jackson streaming | The retained strict ingress prototype matched 81 prior outcomes with a shared Python semantic oracle. This is evidence of parser compatibility, not independent Java semantic validation. |
| Rust/Serde custom visitors | Native ownership and typed decoding are credible for an embedded consumer. Static types alone do not enforce cross-record clock domains, provenance or calibrated truth. |

Current primary sources inspected 2026-10-10:
[Pydantic strict-mode source](https://github.com/pydantic/pydantic/blob/main/docs/concepts/strict_mode.md),
[CUE validation](https://cuelang.org/docs/concept/how-cue-enables-data-validation/),
and [System.Text.Json reader](https://learn.microsoft.com/en-us/dotnet/standard/serialization/system-text-json/use-utf8jsonreader).
The Python, Jackson and Serde sources and exact prototype limits are linked in
the retained [technology experiments](retrospective-v2.md). A requested msgspec
documentation fetch failed; no result or exclusion is inferred from that failure.

**KEEP Python for this component.** The configured implementation supplies the
required byte and numeric semantics with a small explicit validation boundary;
the current finite review reproduces its negative findings. The viable alternatives
do not yet demonstrate a required property or measured improvement absent here.
This is a requirements-specific judgment, not a universal speed ranking, a
build-cost objection or preference based on installation or rewrite cost. A
concrete native consumer, tighter measured allocation budget, sustained throughput
need or proven static contract improvement would reopen the choice. Adding a
model framework would not by itself provide evidence authenticity or authorization.

## Findings and executable correction

The production byte schema and finding rules agree with the reviewed v1 contract;
no production defect was demonstrated. Four new independent test methods cover
gaps in its evidence and make its limitations explicit:

1. Record age may be 100 ms at capture end and capture age another 100 ms at
   evaluation. A successful declaration can therefore describe a 200 ms old
   record. One millisecond beyond either individual gate fails. This is not the
   live runtime freshness gate; thresholds and the frozen v1 wire contract remain
   unchanged.
2. The same input digest can accompany passing and stale reports at different
   caller-supplied instants. It commits manifest bytes, not the evaluation instant,
   caller identity, clock authenticity or report authenticity. Consumers must
   retain the evaluation instant and its provenance separately.
3. Inputs at the maximum integer timestamp and extreme signed clock offsets
   preserve both reference-skew and pair-skew failures without overflow.
4. A foreign clock domain prevents numerical comparison but does not suppress
   an independently bad rig binding. Failure codes remain minimized and fixed.

`python3 -m qualification.technology.review_declarations` runs these tests,
temporarily suppresses each of four distinct negative finding codes, requires
assertion failures with no execution errors, then verifies the restored baseline.
It never edits production source. The retained JSON binds the source files to
the measured result. This is a bounded mutation experiment, not a fuzz campaign.
The README's old compilation-cost rationale is removed and its provenance and
freshness limitations are explicit. Neither tests nor docs upgrade declarations
to hardware evidence.

## Integration and claim boundaries

P17/P18 consumers may use the versioned report only as offline declaration
consistency evidence. It supplies no motion authority, target-selection output,
network access, transport adapter, trusted clock reconciliation or authenticated
authorization. Hash equality is not an MLS/ZTA enforcement mechanism, CNSA
conformance, encryption, five-nines availability or NAF/DoDAF certification.
Those claims require separate contracts and evidence outside this component.
Insufficient information for tactical deployment. Physical calibration,
environmental performance and certification remain external and unverified.

## Artifact byte binding review

The declaration tests were rerun before advancing to this component. Current
`artifacts.py`, its v1 contract and all eight original artifact tests were read
again. The boundary admits only exact built-in dict/string/immutable-byte values,
snapshots the mapping, checks fifteen entries, 1 MiB per value and 4 MiB aggregate,
then uses native SHA-256. It reads no device, file or network. Callers must supply
authorized bytes, must not mutate the mapping concurrently and own any storage
allocated before admission. No thread-safety or memory-admission guarantee is
claimed for caller allocation. There is no hard scheduling deadline.

Fresh technology comparison:

| Candidate | Fit for these constraints |
|---|---|
| Python immutable bytes/native hashlib | Exact immutable ownership and explicit pre-hash budgets avoid payload copies. The GIL may be released during hashing, so rejecting mutable values is significant. |
| Rust owned immutable slices/native SHA-256 | Static ownership is a strong alternative for native consumers. Safe ownership does not authenticate the declared digest or establish what the payload means. |
| Erlang/Elixir immutable binaries/native crypto | Immutable message data fits byte binding. Supervision and distribution provide no required capability to this synchronous offline operation. |
| C# ReadOnlyMemory/native SHA-256 | Read-only access is useful but must be paired with control over backing storage; a view alone does not prove immutable ownership. |
| Node Buffer/native crypto | Mutable views need an owned snapshot or enforced transfer. The earlier alias/copy experiment remains evidence of that distinction, not a whole-validator comparison. |
| Swift Data/Swift Crypto | Value-oriented buffers and portable crypto are credible; a required Swift/native client could favor this boundary. No such deployment constraint has been established here. |

Primary sources inspected again 2026-10-10:
[Python hashlib and GIL behavior](https://docs.python.org/3.13/library/hashlib.html),
[Erlang crypto](https://www.erlang.org/doc/apps/crypto/crypto.html#hash/2), and
[ReadOnlyMemory](https://learn.microsoft.com/en-us/dotnet/api/system.readonlymemory-1?view=net-9.0).
Rust, Node and Swift source links and bounded executable ownership/hash probes
are retained in [the earlier comparison](retrospective-v2.md#artifact-byte-binding).
Those historical timing arrays remain descriptive, not a ranking or current
hardware qualification. No backend certification follows from a hash module name.

**KEEP the current Python/native hash implementation; FIX test coverage and
CLARIFY report lifetime.** Its immutable ownership and measured bounded tests meet
the actual in-process contract without a second payload representation. Alternative
ownership systems are viable, but no missing required property or material measured
gain was demonstrated. The decision is about byte ownership and the trusted boundary,
not familiarity, installed tooling, build steps or rewrite effort. Reopen for a
native consumer ABI, authenticated ingestion contract or demonstrated resource need.

Four new methods verify swapped payload/digest associations, simultaneous expired
calibration plus missing/mismatched/extra bytes, replacement of a caller mapping
after an earlier successful report, and all four distinct 1 MiB payloads at the
aggregate ceiling plus a one-byte-over rejection. Hash success remains independent
of authenticity and physical qualification. No production mismatch was demonstrated.

`python3 -m qualification.technology.review_artifacts` requires the new baseline,
then introduces three temporary negative controls: a constant digest, erased
declaration negatives and a one-byte relaxation of the aggregate budget. Each must
cause an assertion failure, with no execution errors, before the restored baseline
is accepted. Source-bound results are in `artifact-review-v3.json`. These are
bounded synthetic controls, not a concurrent-mutation, field or fuzz qualification.

The contract now states that a prior report does not update when supplied bytes
are replaced and cannot serve as an authorization token. P17/P18 consumers must
reverify the same bytes and independently establish provenance, clock trust,
rights and instrument authenticity. A matched digest grants no operational or
motion authority. Native byte ingestion, transport and crypto certification are
separate peer/external responsibilities, not claims supplied by this API.

Next earliest unreviewed component: P15 campaign coverage and procedures. The
entire lane review and forward software work remain incomplete.
