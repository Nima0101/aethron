# Campaign comparison result review — 2026-10-10

Baseline: `b99af17bb57edc23d0fa18246327e418501ed658`. The review restarted
with the declaration/artifact code and contracts, verified the previous bridge
commit against its retained source observations, then reviewed campaign coverage,
the SQL candidate and the comparison driver. Production coverage semantics still
match the v1 contract; no new production aggregation defect was demonstrated.

## Mismatch and executable correction

The maximum-workload comparison used `evaluate(raw, rows)` as its expected
answer. Agreement could therefore hide a shared wrong result. Ordinary Python
equality also admitted Boolean/float substitutions for counts and flags. Both
allocation-traced calls discarded their results. Focused fault injections ran
the real baseline and duplicate-mutation suites, then changed only benchmark
results: five shared incorrect results, eight type substitutions and four traced
failures all emitted normal evidence. The initial run had 17 assertion failures,
zero errors and zero skips across four methods.

The driver now uses a fixed synthetic oracle independent of either evaluator:
16 cases, four eligible captures per case, 64 submissions, no rejected attempts
or findings, and false qualification/authenticity/domain/procedure flags. It
checks all ten timed results and the allocation-traced result for each candidate.
The artifact tool's exact container/scalar comparison is shared through
`measurement.require_result`; both tools retain their fixed error messages.
Checks run outside timing and allocation tracing. Traced calls retain their
results through a small wrapper, so these allocation figures are descriptive
observations, not directly comparable historical ceilings.

The fixed hashes describe the unchanged synthetic workload. Plan SHA-256 is
`e5d41a943710f3e18d879037e231fc7da7e378c3bea5cf3faa6664042ec90b9b`.
Capture commitment is
`9297849b54d145970ee979df3cb1b2aad5bd066352e8302d67c0d34a4c9f66e2`.
It was independently reconstructed without either evaluator: visit cases in
explicit lexical order `0,1,10,11,12,13,14,15,2,3,4,5,6,7,8,9`, sort the four
SHA-256 hashes of each case's whitespace-distinct manifests, and concatenate
literal `["caseN","digest",1050]` entries after the documented domain prefix.
The resulting hash agrees with the historical v1 observation. That agreement
does not prove independent acquisitions, trusted time or source authentication.

## Technology reassessment

Constraints remain a synchronous offline byte API: at most 16 cases, 64 captures,
4 MiB of input declarations, exact integer/type admission, duplicate-attempt
retention, a permutation-invariant commitment and minimized fixed findings.
There is no durable database, recursive rule requirement, distributed policy
service, device SDK, specified target ABI or hard scheduling deadline here.

| Candidate | Decisive properties for the present component |
|---|---|
| Python Counter and immutable byte inputs | Direct multiplicity counting preserves every submitted occurrence. Exact report types can be checked before delivery without a second serialization boundary. |
| SQLite SQL | GROUP BY/count and joins express duplicate exclusion and coverage. The executable candidate preserves ordinals but constructs an additional relational representation. Native SQLite allocations are excluded from Python tracing. |
| OPA/Rego | Rule composition and separately managed policy are credible for a larger decision service. Arrays preserve multiplicity; sets remove it. This fixed batch contract needs explicit attempt identity, not policy distribution. |
| Soufflé Datalog | Aggregation and static relational analysis are credible alternatives. Relations need explicit attempt ordinals to preserve repeated submissions. Recursive analysis is not required by this report. |
| CUE/schema host or native typed implementation | Shape validation or native ownership could serve a future consumer, but still needs byte commitments, duplicate retention and cross-capture semantics. No measured native deployment requirement has been established. |

Primary sources rechecked:
[Python Counter](https://docs.python.org/3.13/library/collections.html#collections.Counter),
[SQLite aggregates](https://www.sqlite.org/lang_aggfunc.html),
[Rego language](https://www.openpolicyagent.org/docs/policy-language), and
[Soufflé aggregates](https://souffle-lang.github.io/aggregates).
The existing [broader discovery](retrospective-v2.md) supplies additional candidate
context, not newly executed prototypes. Suitability conclusions are engineering
judgments against the stated constraints, not framework certification.

**KEEP Python production aggregation and the SQL comparison candidate; FIX the
measurement oracle.** Direct multiplicity/byte handling meets the contract without
relational or transport re-encoding. The retained ten alternating-order samples
show no demonstrated SQL win requiring migration; they do not establish a general
speed ranking. No executable Rego, Soufflé or native migration is justified by
this workload evidence. Reopen for durable querying, independently deployed rules,
a native consumer ABI or a demonstrated resource requirement. Installation,
familiarity and rewrite cost do not decide this choice.

## Verification and boundaries

[Current evidence](campaign-results-review-v3.json) retains the initial failures,
focused tests, source observations and both candidates' measurements. Additional
controls check that a single bad intermediate timed result cannot be replaced
by later successful calls. Historical results and frozen production bounds are
unchanged. Shared admission/capture semantics mean SQL is not an independent
end-to-end validator; the independent maximum oracle covers only this fixture.

No physical, real-time, availability, MLS, CNSA, Link 16 or customer-readiness
claim follows. Insufficient information for tactical deployment. The next
unreviewed boundary is CLI/report delivery, followed by campaign reference/bundle
consumers. The full audit and P15/P19 acceptance software remain incomplete.
