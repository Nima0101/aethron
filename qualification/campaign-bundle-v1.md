# Campaign coverage and reference report v1

`qualification.campaign_bundle.evaluate(plan_bytes, captures, domain_bytes,
procedure_bytes)` computes [campaign coverage](campaign-v1.md) and
[reference byte matching](campaign-references-v1.md) against the same exact
immutable plan bytes. It accepts raw inputs, never supplied reports or approval
booleans. Run from the source checkout; this harness is not part of the installed
`aethron` wheel. No files, instruments, networks or clocks are opened or sampled.

The existing v1 bounds apply: plan <=65,536 bytes/depth eight; 1–16 cases; <=64
capture entries with immutable manifests <=65,536 bytes each; two exact immutable
references <=1,048,576 bytes each. Thus payload inputs total at most 6 MiB plus
the plan. This is an input-size bound, not a measured process-memory ceiling or
latency guarantee. Caller preallocation is outside admission. The caller must
not mutate the capture list/dicts during the call, as required by the coverage
API. References are checked first; invalid structure raises only fixed
`ValueError("invalid_campaign_bundle")`, with no partial report or input text.

The report has exactly `version` (1), `plan_sha256`, `coverage`, `references`,
`software_checks_passed`, `artifact_bytes_verified`, `artifact_authenticity_verified`,
`domain_verified`, `procedure_verified` and `physical_qualification_passed`.
The nested reports preserve their respective v1 contracts. Both nested plan
commitments and the top-level commitment refer to the identical supplied bytes.
Capture commitments retain submitted multiplicity and caller-supplied instants.

`software_checks_passed` requires both declaration coverage and matching reference
bytes. Structurally valid failures do not short-circuit the other check: duplicate
captures and both reference mismatches all remain visible. The last five flags
above are always false. In particular, matching domain/procedure bytes does not
verify capture artifacts, approve reference content, authenticate instruments or
qualify a device. Missing, stale, unplanned and reused capture findings retain
their existing meaning. Nothing proves independent acquisitions, preregistration,
trusted time, complete submission, rights, field accuracy or certification.

The report omits opaque reference content and retains only the existing aggregate
metadata and commitments. Digests/counts remain linkable; this is not anonymization.
The mutable returned dictionary is not an authenticated receipt or authorization
token. Recompute from authorized original inputs before relying on its results.
The bundle grants no motion authority or operational capability to peer consumers.

For separate capture-artifact checks, pass each original manifest and its same
evaluation instant to `qualification.artifacts.verify`. Retain the full submitted
capture list, including failed and reused attempts, when computing the bundle.
Passing artifact checks cannot replace campaign coverage. Conversely, bundle
success says nothing about supplied artifact bytes. Keep both reports and their
negative findings; do not overwrite the bundle's permanently false flags.

An artifact report's nested `input_sha256` binds only that manifest's exact bytes.
It does not bind the evaluation instant, case assignment, campaign or provenance.
The campaign's `captures_sha256` binds the complete submitted multiset of case,
manifest digest and instant. A consumer must retain those original inputs and
recompute at the intended instant; selecting an old passing report by artifact
digest alone can associate it with a different or stale manifest. Even all
software checks passing does not authenticate instruments or qualify hardware.
See the [composed API checks](technology/bundle-artifact-integration-v3.md).

## Technology decision and baseline review — 2026-10-10

The preceding declaration, artifact, campaign, CLI/comparison and reference-binding
components were reread from earliest implementation through `992c987`; 75 focused
tests passed. Their current immutable ownership, strict schema, multiplicity and
negative-evidence constraints still support the recorded KEEP choices. The bridge
commit fixes comparison document fidelity; it does not change production admission.
The existing [review](technology/review-v3.md) records the broader component-specific
candidate comparisons. No additional production mismatch was demonstrated here.

For this composition, requirements are synchronous bounded raw-byte evaluation,
one plan identity, preservation of both versioned results, fixed private errors
and no persistence, rule distribution, target ABI or hard deadline. Candidates:

| Candidate | Fit and decisive tradeoff |
|---|---|
| Python direct function composition | The same immutable byte object reaches both validators, with no serialization or payload copy between stages. Exact native values and both negative reports remain available. |
| OPA/Rego | Declarative conjunction is suitable for independently deployed policies. It still needs byte-preserving adapters and capture multiplicity handling; this fixed conjunction requires no policy distribution. |
| CUE constraints plus a host | Strong declarative validation/unification is credible for plan evolution. Raw byte commitments and executing both existing validators still need a host boundary. |
| Rust owned typed orchestration | A credible native boundary with static ownership. It requires an interoperable binding or parity-tested independent validators; no native ABI or measured resource requirement currently favors it. |
| SQLite relational composition | Useful when durable submissions and queryable history are required. This function persists nothing and combines two bounded results without relational joins. |

**SELECT Python direct composition.** The decisive property is preservation of the
single immutable plan and existing result contracts without an extra representation
boundary. This choice is not based on installed tooling, familiarity or rewrite
cost. A native integration, independently managed rule set, persistence requirement
or measured resource deficit would reopen it. No performance ranking is inferred.

Primary sources consulted for the current decision:
[Python immutable bytes](https://docs.python.org/3.13/library/stdtypes.html#bytes-objects),
[Rego policy language](https://www.openpolicyagent.org/docs/policy-language), and
[CUE validation](https://cuelang.org/docs/concept/how-cue-enables-data-validation/).
The earlier [campaign technology review](technology/review-v3.md#campaign-coverage-and-procedures-review)
retains SQLite/native alternatives and their executable comparisons. These sources
describe language properties; the suitability judgment is this component's analysis.

Seven focused methods cover all four conjunction outcomes, simultaneous negatives,
exact plan byte identity, time/multiplicity commitments, malformed/forged/oversized
inputs, content minimization and the combined input ceilings. The original six
methods first failed with thirteen assertions and zero errors before implementation.
Source-bound results and the conjunction mutation are retained in
`evidence/campaign-bundle-verification-v1.json`. Tests use synthetic declarations;
hardware/field qualification and hosted execution remain separate evidence gates.
