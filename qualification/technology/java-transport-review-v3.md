# Java probe transport and SQL aggregation review v3

Reviewed from the declaration boundary through the audit probes at baseline
`b65783d9198f456d405025d6a8cf612ce456cbdb`. The declaration, artifact and campaign
review controls plus SQL contract tests passed 24 methods. The preceding probe
provenance commit and its immutable-tree Markdown links were verified. These are
software checks; P4/P15 physical, domain, procedure and authenticity gates remain
external. The complete lane review is still open.

## Requirements and technology reassessment

The Java component is a finite offline Jackson ingress experiment: at most 256
hexadecimal request rows and 8 MiB of transport; decoded documents are bounded to
65,536 bytes and nesting depth eight. It returns one JSON response per request.
It has no device SDK, network, service authorization or real-time deadline. Its
Python comparison checks document preservation and uses the same production
semantic oracle; it is not an independently implemented Java qualification engine.

| Candidate | Decisive fit for this component |
|---|---|
| Java/Jackson streaming with a byte-level row precheck | Exercises the actual alternate parser, duplicate detection and bounded token stream. A framing defect can be corrected without changing the semantic oracle. |
| C#/F# with System.Text.Json | A credible forward-only UTF-8 reader for a separate candidate; it needs explicit duplicate, framing and semantic checks. It would measure a different parser, rather than verify Jackson. |
| Rust with Serde visitors | Credible native typed decoding with ownership; custom visitors and transport handling still need contract tests. No target native deployment requirement or measured win has been established here. |
| JavaScript/Node JSON.parse | The retained experiment has four duplicate-key mismatches; it is a negative comparator, not a conforming replacement. |

**KEEP Java for the Jackson experiment; FIX its request framing.** This is a
scope-specific decision, not a production runtime ranking. Java's default
[String split](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#split(java.lang.String))
discards trailing empty elements. The alternatives were reconsidered using the
[System.Text.Json reader](https://learn.microsoft.com/en-us/dotnet/standard/serialization/system-text-json/use-utf8jsonreader)
and [Serde](https://serde.rs/) primary documentation. Choosing the runtime whose
parser is being tested is the review's inference; no unexecuted alternative is
claimed slower or incorrect.

The SQL component independently expresses campaign aggregation for at most sixteen
cases and sixty-four attempts, after shared Python admission and per-capture
findings. The required properties are retention of every attempt ordinal,
duplicate rejection across cases, all negative findings, stable case order and
identical byte commitments. No persistent store, recursive inference or remotely
editable policy is required.

| Candidate | Decisive fit for this component |
|---|---|
| Python Counter and explicit passes | Direct multiplicity accounting and a bounded report without a query engine; remains the production implementation. |
| SQLite SQL with ordinal primary keys | A distinct relational aggregation for comparison; parameterized values, fixed SQL, private in-memory connection closed after each call. |
| Soufflé/Datalog | Credible typed relations and aggregate logic; attempt ordinals must be retained to prevent set semantics from collapsing duplicate submissions. Recursive rules do not serve this small fixed aggregation. |
| Rego/OPA | Credible declarative policy decisions over structured data; still requires exact-byte commitments, multiplicity preservation and bounded input admission. No distributed policy lifecycle is required here. |

**KEEP Python production aggregation and the SQLite audit comparator.** Fresh
execution covered eleven SQL test methods, forty-eight comparator invocations and
three assertion failures from the duplicate-admission mutant, with zero mutant
errors. Ten alternating-order maximum-count comparisons also matched. These
checks establish the comparator's usefulness; they do not independently validate
shared admission helpers or prove global superiority over unexecuted runtimes.
The production path already represents the required multiplicities directly;
adding a rule/query engine has no demonstrated contract, deployment or performance
advantage for this bounded workload. This is a requirement-specific judgment,
not protection of the incumbent language. Primary sources inspected:
[Counter](https://docs.python.org/3/library/collections.html#collections.Counter),
[SQLite in-memory databases](https://www.sqlite.org/inmemorydb.html),
[Soufflé](https://www.souffle-lang.com/tutorial), and
[Rego](https://www.openpolicyagent.org/docs/policy-language).

## Executable correction and evidence limits

Previously, trailing empty request rows disappeared before the 256-row check.
For example, 257 LF bytes produced no responses and exited successfully. A valid
row followed by blank rows also lost rejection responses. Empty input instead
produced one rejection for a request that was not present.

The corrected probe counts LF-terminated rows plus any final unterminated row
before allocating the split array. Over 256 rows fails before any response.
Splitting preserves empty elements, and the loop processes the counted rows.
Empty transport has zero requests. One terminal LF terminates the preceding row;
every additional LF represents an empty request and receives `accepted:false`.
The existing aggregate byte cap and JSON admission logic are unchanged. The
transport remains a trusted synthetic audit interface: it is not a private-error
production endpoint, and it does not impose an I/O wall-clock timeout.

Six process tests require an explicit compiled classpath, fail rather than skip
when unavailable, and run only in the optional Java CI job. The compiled baseline
produced five assertion failures with zero errors. After correction all six pass;
over-budget tests additionally require the expected Java exception so VM startup
failures cannot count as successful rejection. The existing 81-request experiment
still matches both documents and semantic reports.

One compiler attempt, one test run and one actionlint run encountered host thread
exhaustion. Reduced-thread/sequential retries passed. These failures are retained
as environment limitations, not counted as successful negative controls. The
recorded timings describe this shared host only; Python tracing excludes native
SQLite allocations. The Jar digest was checked against the workflow pin; source
and compiled-class fingerprints are reproducibility locators, not authenticated
execution attestations. Prior result files remain unchanged.

Raw comparison results, current source bindings and test outcomes are in
[java-transport-review-v3.json](java-transport-review-v3.json).
