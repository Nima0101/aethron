# Qualification implementation review v3 — in progress

This is an implementation review record, not a replacement governance policy.
The review starts at the earliest declaration component in commit `eebfad47`
and covers the lane built through `a5158617`. Earlier decisions are evidence
inputs only. No audit-complete marker or physical qualification is asserted.

| Historical component | Current review state |
|---|---|
| Rig, calibration, clock, environment declaration validator | KEEP implementation; FIX evidence coverage; CLARIFY claims |
| Artifact byte binding | Pending fresh review |
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

Next earliest unreviewed component: artifact byte binding. The entire lane review
and forward software work remain incomplete.
