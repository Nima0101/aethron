# Qualification implementation review v3

This is an implementation review record, not a replacement governance policy.
The review starts at the earliest declaration component in commit `eebfad47`
and includes the later CLI and audit-tool corrections accompanying this record.
Earlier decisions are evidence inputs only. Review of the built components does
not establish completion of all future qualification software or physical qualification.

| Historical component | Current review state |
|---|---|
| Rig, calibration, clock, environment declaration validator | KEEP implementation; FIX evidence coverage; CLARIFY claims |
| Artifact byte binding | KEEP implementation; FIX evidence coverage; CLARIFY report lifetime |
| P15 campaign coverage and procedures | KEEP implementation; FIX evidence coverage; CLARIFY unknown-case and provenance claims |
| CLI/report delivery and verification tooling, including audit probes | KEEP configured runtimes; FIX CLI/response admission, source bindings and hosted controls |

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

## Campaign coverage and procedures review

The earlier declaration and artifact review controls pass again before this
component is reviewed. The deployed interface remains a synchronous source-checkout
API accepting at most sixteen cases and sixty-four immutable manifest byte strings,
each at most 65,536 bytes. It performs no capture, database persistence, networking,
clock sampling or device access. Constraints are exact input admission, retention
of every submitted occurrence, fixed negative findings, integer counts and a
permutation-invariant byte/time commitment. No hard deadline, durable campaign
ledger, rule distribution or recursive query requirement exists for this interface.

Fresh domain-specific candidate comparison, including non-incumbent technologies:

| Candidate | Decisive properties for this contract |
|---|---|
| Python Counter, sets of findings and ordered triples | Multiset counts retain repeated inputs while finding sets minimize diagnostics. Immutable bytes are hashed directly; no relational re-encoding is necessary. |
| SQLite SQL aggregation | GROUP BY/count and LEFT JOIN express duplicate rejection and missing coverage. The executable candidate preserves each ordinal and uses parameterized values. Its tables/views add a second representation but enable relational queries if the deployment later needs them. |
| OPA/Rego | Declarative relations and rule composition fit larger policy sets. Arrays retain duplicates; sets do not. A correct adapter must preserve attempt ordinals and exact manifest bytes before policy evaluation. No policy-bundle distribution or independently configurable rule set is required here. |
| Soufflé Datalog | Aggregate queries fit relational coverage analysis; explicit attempt identity is needed to retain repeated submissions. Recursive/fixed-point analysis offers no required advantage for this bounded one-pass report. |
| CUE/JSON Schema plus a host | Useful for plan shape constraints; raw immutable manifests, cross-capture multiplicity and the versioned commitment still need procedural handling. |
| Rust or C# native/typed aggregation | Static representations are credible when a native ABI or measured memory/throughput constraint is required. Neither typing nor native compilation proves completeness of submitted evidence. No such deployment constraint or measured gain is demonstrated here. |

Current primary sources inspected 2026-10-10:
[Python Counter](https://docs.python.org/3.13/library/collections.html#collections.Counter),
[SQLite aggregate semantics](https://www.sqlite.org/lang_aggfunc.html),
[Rego arrays and sets](https://www.openpolicyagent.org/docs/policy-language), and
[Soufflé aggregates](https://souffle-lang.github.io/aggregates).
The earlier [candidate comparison](retrospective-v2.md) retains the remaining
ecosystem sources and bounded maximum-size experiment. These sources support
language properties; the suitability judgments above are this component's analysis.

**KEEP Python aggregation; FIX independent coverage; CLARIFY claims.** The direct
multiset/immutable-byte representation meets this exact contract with fewer
representation transitions than the tested SQL composition. SQL is a viable
alternative, with shared input/capture semantics and independently implemented
aggregation, not an independent end-to-end validator. Its historical timing samples
do not establish a performance ranking. No missing required property or material
measured advantage warrants migration. Reopen for durable evidence retention,
independent policy deployment, native integration or a demonstrated resource bound;
installation, familiarity and rewrite cost do not decide this choice.

Five new methods assert outcomes independently and compare both implementations:
an unknown-case duplicate still invalidates the planned occurrence even with a
different evaluation instant; a literal commitment preimage retains identical
triples and sorts times numerically; satisfied minimums do not erase malformed or
unplanned attempts; domain/procedure hash changes bind the plan without verifying
referenced contents; and whitespace-distinct declarations may satisfy coverage
without demonstrating separate acquisitions. No production defect was demonstrated.

`python3 -m qualification.technology.review_campaign` runs these controls, introduces
three temporary mutations (erased duplicate counts, deduplicated commitment triples,
and SQL duplicate admission), requires assertion failures without execution errors
or skips, and reruns the restored baseline. `campaign-review-v3.json` binds these
results to the sources. No long soak, physical run or full fuzz campaign is implied.

The contract previously implied all entries undergo declaration validation and
called committed instants trusted. It now states the actual behavior: unknown-case
bytes are rejected, hashed and duplicate-counted without declaration evaluation;
clock provenance remains the caller's responsibility. The checker cannot establish
preregistration or detect failed attempts omitted before invocation. These are
limits of an offline report, not authorization or qualification grants to P17/P18.

## CLI report delivery review

This source-checkout command transforms bounded stdin bytes into one deterministic
JSON report and a 0/1/2 exit status. It needs the declaration API's exact semantics,
fixed private errors, one caller-chosen evaluation instant and unchanged golden
report bytes. It has no interactive UI, plugin system, remote commands or native
executable distribution requirement. A slow stdin pipe or stdout consumer is not
given a wall-clock deadline by the byte-size limit; supervision belongs to the caller.

Fresh candidates inspected 2026-10-10:

| Candidate | Requirements-based comparison |
|---|---|
| Python argparse plus explicit action | Direct invocation of the reviewed byte API and explicit errors preserve the boundary. Default abbreviation and last-value-wins behavior require correction. |
| Python Click | Typed options and multiple-value policies are useful for complex CLIs. This single-option command still needs explicit cardinality and privacy behavior; the framework adds no required command composition here. |
| Rust clap | Set actions reject duplicate arguments by default unless override is enabled. A strong native CLI candidate; it would also need a reviewed binding to the current declaration API or independently verified semantic implementation. |
| Nushell custom command | Typed parameters and structured pipelines fit operator scripting. The host boundary must still preserve raw bytes, fixed errors and the library's JSON report/exit conventions; a structured shell is not required by this noninteractive command. |

Sources: [argparse actions and abbreviation](https://docs.python.org/3.13/library/argparse.html),
[Click options](https://click.palletsprojects.com/en/stable/options/),
[clap ArgAction](https://docs.rs/clap/latest/clap/enum.ArgAction.html), and
[Nushell custom commands](https://www.nushell.sh/book/custom_commands.html).
These are viable alternatives rather than an exhaustive language list. The choice
is not based on installed tools, familiarity or rewrite cost.

**KEEP the thin Python entry point; FIX ambiguous argument admission.** Direct
library invocation avoids adding a second report/byte conversion boundary, while
a small argparse action supplies the same required duplicate rejection available
in native parsers. No native deployment or measured throughput requirement makes
another runtime materially better for this command. Retain exact golden output;
reopen if a standalone distribution or a measured startup budget is required.

The retained RED run had six assertion failures and zero errors: three abbreviated
time options were accepted, and all three repeated-option forms used the last
value. In particular, `--now-ms 1151 --now-ms 1050` changed a stale evaluation into
a passing report. The parser now disables abbreviation and rejects a second time
option, even when values match, before reading input. Separate and equals forms
with one value still reproduce both golden reports with their original exit codes.
Invalid argument errors remain fixed and contain no supplied text. JSON schema,
freshness thresholds and library behavior are unchanged. `cli-review-v3.json`
records the before/after evidence and source bindings.

## Audit probes, evidence integrity and hosted verification

This final historical component runs finite synthetic corpora, compares parser/hash/
aggregation candidates, distinguishes assertion failures from execution errors, and
emits source-bound JSON. It has no device interface, latency acceptance deadline or
external artifact authenticity claim. The source-checkout Python 3.9/3.13 test
boundary and GitHub-hosted checks are actual deployment requirements. Small local
probes are permitted; no full clone, repository matrix, VM, long fuzz or soak is used.

Fresh technology comparison:

| Candidate | Decisive properties |
|---|---|
| Python unittest and explicit JSON orchestration | Directly exercises the reviewed Python APIs and their typed failure results. Finite mutation controls can distinguish assertion failures, errors and restored behavior without encoding API objects through another runtime. |
| pytest | Can execute unittest cases and offers fixtures and parametrization. Those capabilities are credible but do not replace strict response parsing, source binding or independent assertions; the current finite harness needs no additional fixture/plugin lifecycle. |
| Node test runner | Provides another structured test/reporting ecosystem. It is appropriate for JavaScript-native boundaries; driving these Python semantic APIs needs an explicit adapter and preservation of error/byte semantics. |
| JVM/JUnit or .NET/NUnit | Typed assertions and test engines are credible alternatives, including C# outside the present probe languages. They do not remove the need for a checked Python bridge or independently implemented semantic oracle. |
| GitHub workflow YAML | The selected hosted platform consumes this format. Generating it from another language adds an unchecked generation boundary unless separately verified; no such generation requirement exists here. |

Primary sources inspected 2026-10-10:
[unittest results](https://docs.python.org/3.13/library/unittest.html#unittest.TestResult.wasSuccessful),
[pytest unittest support](https://docs.pytest.org/en/stable/how-to/unittest.html),
[Node test runner](https://nodejs.org/api/test.html),
[JUnit platform](https://docs.junit.org/6.1.3/overview.html),
[NUnit assertions](https://docs.nunit.org/articles/nunit/writing-tests/assertions/assertions.html),
and [GitHub artifact retention](https://docs.github.com/en/actions/tutorials/store-and-share-data).
Suitability conclusions are this review's analysis, not claims made by those sources.

**KEEP Python orchestration, Java/Jackson streaming and Node primitive probes,
SQL comparison, and native workflow YAML; FIX evidence boundaries.** The configured
languages directly expose the properties under comparison. Python's direct API
and result access best fits the orchestration contract; replacing the harness
framework does not fix ambiguous response interpretation. Java remains an audit
parser with a shared Python semantic oracle, SQL an independently implemented
aggregation with shared admission/semantics, and Node a limited primitive/negative
probe. No probe becomes production admission through this decision. No migration
has demonstrated a missing required capability or material measured improvement.
This is not an installation, compilation-cost or familiarity preference.

Six new audit-report methods cover source dependencies, exact Boolean response
flags, duplicate/unknown/missing response fields, malformed transport values,
response row counts and an always-rejecting candidate. The initial five-method
RED run had eight assertion failures and one `KeyError` for a missing document.
The corrected reader requires exact envelope keys and rejects duplicate JSON keys;
it checks the row count before parsing rows. The existing 8 MiB response-file cap
remains unchanged. This is a trusted synthetic test transport, not a newly exposed
general-purpose input service. A valid response envelope does not authenticate its
producer or prove which executable generated it.

Ingress evidence now also binds the shared byte/depth guard and padded benchmark
fixture; artifact measurement binds the declaration evaluator and byte/depth guard.
These hashes cover the listed application dependencies, not a complete operating
system, interpreter or cryptographic supply-chain attestation. Historical records
remain unchanged. All 59 declared source bindings in eleven retained reports were
matched against current bytes or a recorded Git version; a historical match is not
a current-source test pass.

Fresh bounded execution retained Java composition parity for all 81 requests,
Node's four known duplicate-key failures, four-payload Python/Node hash agreement,
and all ten V3 negative controls. The pinned 594,187-byte Jackson artifact was
hash-checked before local compilation. Timings remain descriptive shared-host
measurements; no cross-runtime ranking, real-time bound or hardware claim follows.
The aggregate result and source hashes are in `audit-tool-review-v3.json`.

The hosted workflow now executes all three V3 negative-control drivers for each
supported Python version and retains their reports for seven days, alongside the
existing pinned parser and primitive comparisons. Workflow configuration and local
actionlint success do not establish hosted execution success. The current review
is caught up through these built components; physical/legal review, authenticated
evidence and further qualification software remain separate work.

## Follow-up: parser document fidelity — 2026-10-10

The fresh walk reread declaration validation, artifact binding, campaign coverage,
CLI delivery, comparison tooling and campaign reference binding through `5f0f3a7`.
All 71 existing focused methods passed. The earlier component constraints and KEEP
choices still apply: exact immutable byte ownership, bounded offline inputs, fixed
negative findings and no device, network, native ABI or hard-deadline requirement.
The reference checker retains its separately documented immutable/native-hash
choice and false qualification flags. This review found an executable mismatch
in the comparison tooling, so forward campaign composition remains the next task.

Summary-report parity did not demonstrate document preservation. The comparator
replaced the candidate's input hash with the original hash before comparing
summaries. Changed capture instants and clock-domain strings could disappear from
the summary. Two different invalid documents could also produce the same fixed
schema error. Earlier 81-request results establish only their recorded outcome
parity; they do not establish the additional document-fidelity property below.
Those historical reports are retained unchanged.

The audit transport needs to compare decoded JSON values, ignore object key order
and insignificant spelling, distinguish integer/float/Boolean representations,
and reject ambiguous original JSON. It has no signing or cross-runtime canonical
byte requirement. Current domain-relevant options were reassessed:

| Option | Decisive property |
|---|---|
| Python sorted JSON encoding after strict decoding | Preserves integer/float/Boolean distinctions of the configured Python oracle, normalizes object order, and avoids an additional runtime conversion. `allow_nan=False` rejects nonfinite decoded values. |
| Recursive exact-type comparison | Viable and avoids temporary serialization, but needs explicit scalar, object, sequence and finite-number rules. No measured allocation constraint requires that additional comparison implementation here. |
| Node strict deep equality | Distinguishes Boolean from number, but JSON parsing maps integer and floating spellings to the same Number type. A token-preserving adapter would still be needed for this oracle. |
| C# System.Text.Json DeepEquals/token reader | A credible independent typed JSON ecosystem. Deep equality alone is not evidence of this profile's integer-token, duplicate and encoding rules; a configured token reader and adapter require parity evidence. |
| RFC 8785 canonical JSON | Intended for invariant cryptographic serialization. Its numeric normalization is not the integer-versus-float distinction required here. This audit does not need a signing format. |

Sources inspected: [Python JSON hooks and serialization](https://docs.python.org/3.13/library/json.html),
[Node strict assertions](https://nodejs.org/api/assert.html),
[System.Text.Json deep equality](https://learn.microsoft.com/en-us/dotnet/api/system.text.json.jsonelement.deepequals?view=net-9.0),
and [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785).
The suitability conclusions are this review's analysis. **KEEP Python orchestration;
FIX document preservation checks.** Installed tools, familiarity and rewrite cost
are not selection criteria. Reopen for a measured allocation constraint or a
standalone comparison service with a different token contract.

Every accepted candidate response now gets a separate comparison to its original
bounded UTF-8 input with duplicate-key rejection and bounded integer conversion.
Sorted encoding compares decoded values before lossy report projection. Integer
`-0` and `0`, escaped names and reordered object keys remain equivalent. Floating
spellings are compared as Python decoded values, not arbitrary-precision lexical
numbers; valid qualification manifests contain no floats. This is not canonical
signing, response authentication or proof of parser behavior outside the corpus.
Rejected candidate rows are covered by outcome comparison, not by a claim that
there was a returned document. `all_documents_match` is vacuous if none is accepted;
`all_reports_match` and the process exit must also be checked.

Reports retain `mismatch_indices` as the union of failures and add
`report_mismatch_indices`, `document_mismatch_indices` and `all_documents_match`.
`all_reports_match` continues to describe summary equality alone. Exit zero requires
both kinds of equality. The transport's existing 8 MiB bound remains unchanged;
comparison may allocate temporary encoded strings within that finite workload and
has no wall-clock guarantee. Four new test methods retain eight negative assertions
and a key-order/negative-zero positive control. See `document-fidelity-review-v3.json`
for RED/GREEN, bypass-mutation and fresh Java composition evidence. No physical or
production qualification follows.
