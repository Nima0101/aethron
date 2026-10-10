# Retrospective technology audit, policy 2 — in progress

This audit covers the existing qualification software in historical order:
declaration validation (including rig, calibration, clock and environment
rules), artifact byte binding, campaign coverage, then CLI/report delivery and
verification tooling. Declaration validation, artifact binding and campaign coverage
have policy-2 KEEP decisions below; delivery/tooling remains open.
Earlier technology notes are hypotheses to reassess, not completion evidence.
No new qualification capability or physical result is claimed by this audit.

## Declaration validator: operational constraints

This is an offline source-checkout library and stdin CLI. Its untrusted UTF-8
input is bounded to 65,536 bytes, depth 8, five sensors and fifteen records.
Duplicate keys must be rejected after escape decoding. Integers, decimal and
exponent tokens cannot silently interchange; timestamps have an exact bounded
integer domain. Exact input bytes and canonical rig bytes have separate hash
commitments. Fixed errors must not echo input. Negative calibration, timing,
binding and missing-evidence findings must survive report generation.

The deployment has no device SDK, actuator interface or hard real-time deadline.
The frozen 100 ms freshness gate describes evidence age, not permissible CLI
processing latency. Runtime startup, bounded allocation, portability and ongoing
dependency maintenance matter; no language receives preference because it is
installed. Both syntax admission and semantic findings require migration parity.

## Candidate discovery and decisive properties

| Candidate | Supporting property | Remaining obligation |
|---|---|---|
| Python standard library | Pair and numeric-token hooks preserve the distinctions needed at ingress. | Defaults are permissive; independently verify custom bounds, exact types, and full rule behavior. |
| CUE | Closed definitions and relational constraints can express schema and field relationships. | Check duplicate-field unification and numeric lexical behavior before treating it as the raw evidence boundary; hash/report orchestration also needs evaluation. |
| TypeScript with Ajv | Compiled closed-shape and conditional validation; source-aware JSON revivers can examine number spelling. | Revivers still lose duplicate members in the measured configuration; an additional tokenizer would need assessment. |
| C# System.Text.Json | UTF-8 span reader permits low-allocation token admission with static types. | Prototype duplicate tracking, numeric token inspection, byte/depth bounds and fixed error conversion. |
| Java/Jackson | Streaming constraints and explicit duplicate detection are available. | Check exact byte caps outside library document-length constraints, token typing and deployment resource behavior. |
| Rust/Serde | Typed numeric representations and custom visitors support strict decoding. | Test duplicate handling in the chosen deserializer, bounded arithmetic and the complete finding/report contract. |
| Go encoding/json | Token iteration and number-token preservation are available. | Default object decoding is insufficient; evaluate configured duplicate, UTF-8, lexical number and schema admission. |

Primary sources inspected 2026-10-10:

- [Python JSON hooks, defaults and limits](https://docs.python.org/3.13/library/json.html).
- [CUE validation](https://cuelang.org/docs/concept/how-cue-enables-data-validation/)
  and [language semantics](https://cuelang.org/docs/reference/spec/).
- [Ajv schema support](https://ajv.js.org/json-schema.html) and
  [ECMAScript JSON parsing](https://tc39.es/ecma262/multipage/structured-data.html#sec-json.parse).
- [System.Text.Json UTF-8 reader](https://learn.microsoft.com/en-us/dotnet/standard/serialization/system-text-json/use-utf8jsonreader).
- [Jackson streaming constraints source](https://github.com/FasterXML/jackson-core/blob/3.x/src/main/java/tools/jackson/core/StreamReadConstraints.java),
  [duplicate detection](https://fasterxml.github.io/jackson-core/javadoc/2.14/com/fasterxml/jackson/core/StreamReadFeature.html)
  and [document-length advisory](https://github.com/FasterXML/jackson-core/security/advisories/GHSA-2m67-wjpj-xhg9).
- [Serde JSON number representation](https://docs.rs/serde_json/latest/serde_json/struct.Number.html).
- [Go JSON package](https://pkg.go.dev/encoding/json).

## Executable ingress evidence

`ingress-vectors-v1.json` contains eighteen exact-byte synthetic cases, encoded
as hexadecimal for reuse across languages. Expected rejection and findings are
literal contract expectations. Accepted incomplete declarations retain all three
missing-evidence findings; acceptance is not a qualification pass.

```sh
python3 -m unittest qualification.tests.test_ingress_audit -v
node --v8-pool-size=1 qualification/technology/ingress-probe.mjs
```

The test initially failed because the portable corpus was absent. With the corpus,
the production validator matches all eighteen expectations on Python 3.13.5.
Removing duplicate detection, accepting integral floats or decoding malformed
UTF-8 permissively would break these cases.

The Node 22.23.2 prototype uses fatal UTF-8 decoding, retains the BOM for rejection,
checks a source-aware numeric reviver, and limits byte length and integer tokens.
It matches fourteen cases but accepts four prohibited duplicate-member cases:
equal values, overwritten values, escaped names, and nested duplicates. The
negative result is retained in `ingress-node-result-v1.json`. Modern revivers do
preserve numeric source spelling here; dismissing JavaScript solely for losing
integer-versus-decimal spelling would be incorrect.

The probe is deliberately **not** a full alternative validator: it has no schema,
depth gate, timing rules or reports. It is not imported by production software,
and its successful process exit does not mean parity. This evidence rules out
this parser configuration as a drop-in replacement; it does not rule out other
JavaScript parsers, and does not establish Python as the overall winner.

Local sandbox process/namespace allocation failed during the audit and later
recovered intermittently. No latency comparison is credible from this run.
Two initial Jackson documentation requests failed; the sources above were
located subsequently. These limitations remain part of the audit record.

## Strict streaming experiment and declaration decision

`IngressProbe.java` implements the alternative ingress boundary with Jackson
2.21.5: explicit input-byte cap, reporting UTF-8 decoder, duplicate detection,
depth/number limits, integer tokens and one root value. It is audit-only code,
not a parallel production validator. The dependency is 594,187 bytes, pinned to
SHA-256 `b64b5874162b503a0e58a8f7758266e8dd9f91bf49e3a59ae0b5f47589a231b7`.
This version is beyond the patched versions in the document-length advisory;
the prototype also checks the exact byte length itself.

`compare_ingress.py` exports the same eighteen vectors plus 63 calls collected
while executing the existing schema/timing tests. Java parses these bytes; the
comparison applies the unchanged Python semantic validator to its output and
retains the original input-byte commitment. All 81 outcomes match. This establishes
frontend compatibility for this corpus, **not** an independent Java implementation
of calibration, clock, environment or report logic. The Python oracle tests retain
their independently specified expectations. The experiment would fail if duplicate
keys or integral float tokens were admitted, required findings changed, or input
byte commitments were dropped. `ingress-java-result-v1.json` binds source and
transport hashes and retains execution limitations.

Twenty Python calls at the full 65,536-byte input boundary had median 5.813 ms,
maximum 64.194 ms, and a separate single-call tracemalloc peak of 73,615 bytes
(preconstructed input excluded). These are descriptive measurements on a shared
host, not a frozen threshold, hard-real-time guarantee or cross-language speed
ranking. Java startup intermittently failed creating native threads. Sequential
export/run/compare succeeded with JIT disabled and a 64 MiB heap cap. This host
failure is not evidence against Java as a language. Hosted reproduction has been
added; workflow existence is not a hosted PASS.

**Decision: KEEP Python for declaration validation.** Ranking priorities are
strict evidence interpretation and deterministic findings, then a small auditable
admission boundary and bounded resource use for a one-shot offline tool. Python
provides immutable input bytes, exact integer arithmetic, object-pair hooks and
separate numeric token types; explicit caps and exact type checks close its
permissive defaults. The existing bounded implementation passes the portable
corpus and semantic tests. Jackson proves a viable strict alternative but adds
an external parser plus UTF-8 and object-conversion plumbing without an observed
contract improvement here. CUE/Ajv improve schema expression but still require
a distinct strict byte boundary and procedural timing/hash/report logic. Go,
Serde and System.Text.Json can implement that boundary, but their static types
do not alone enforce duplicate rejection, cross-field clock-domain checks or
evidence provenance. They need application validation as well.

This decision follows the operational fit and trusted-code/dependency surface,
not installed tools, familiarity, rewrite effort, or a claim that Python wins
throughput. A required embedded/native binary, sustained batch throughput,
memory ceiling below the measured envelope, or a proven static contract that
eliminates an actual validation defect would reopen it. No alternative has
demonstrated a material win for the current offline contract, so no production
migration is prescribed for this component.

To reproduce the strict comparison with JDK 17 or later and the pinned jar in
an audit scratch directory (no library installation is needed):

```sh
javac -cp "$QUALIFICATION_AUDIT_DIR/jackson-core.jar" -d "$QUALIFICATION_AUDIT_DIR" qualification/technology/IngressProbe.java
python3 -m qualification.technology.compare_ingress --export > "$QUALIFICATION_AUDIT_DIR/requests.hex"
java -Xint -XX:ActiveProcessorCount=1 -XX:+UseSerialGC -Xmx64m -cp "$QUALIFICATION_AUDIT_DIR:$QUALIFICATION_AUDIT_DIR/jackson-core.jar" IngressProbe < "$QUALIFICATION_AUDIT_DIR/requests.hex" > "$QUALIFICATION_AUDIT_DIR/responses.jsonl"
python3 -m qualification.technology.compare_ingress --responses "$QUALIFICATION_AUDIT_DIR/responses.jsonl"
```

Python is used for experiment orchestration because the semantic oracle exposes
Python objects and exceptions. Keeping those calls in-process avoids altering
the oracle through a second wire representation. This is an instrumentation
choice, not a presumption about the production language.

## Artifact byte binding

Constraints: at most fifteen immutable byte values, 1 MiB each, 4 MiB total;
SHA-256 equality for every referenced value; exact byte/type admission and a
mapping snapshot; retain missing, extra, corrupt and declaration-negative evidence.
No filesystem traversal, network fetching, instrument authentication, timing
deadline or crypto algorithm design belongs to this API. The language boundary
must not let a mutable alias change content while native hashing releases an
interpreter lock or operates in another worker.

Candidate comparison, from current official ecosystems:

| Candidate | Decisive property and fit |
|---|---|
| Python bytes + hashlib | Immutable byte values and native hashing directly satisfy the ownership boundary; exact types intentionally reject mutable bytearray/memoryview inputs. |
| Node Buffer + crypto | Native SHA-256 is suitable. Views alias mutable storage; ownership needs an explicit copy or a separately enforced transfer protocol. |
| Rust owned slices/Arc + SHA-256 | Ownership and immutable shared slices are a strong static alternative. A native standalone distributor or high-throughput pipeline could favor this design; neither is required by this bounded in-process API. |
| C# ReadOnlySpan + SHA256 | Efficient read-only view, but view access does not establish ownership of the backing memory. A producer/consumer ownership rule is still required. |
| Swift Data + Swift Crypto | Value semantics and cross-platform crypto are credible; the Linux package brings its own crypto implementation/build boundary without an Apple SDK requirement here. |
| Erlang/Elixir binaries + crypto | Immutable binary values and native crypto fit the byte boundary; actor supervision/distributed execution offer no required benefit for a synchronous bounded calculation. |

Sources: [Python hashing](https://docs.python.org/3.13/library/hashlib.html),
[Node crypto](https://nodejs.org/api/crypto.html#cryptocreatehashalgorithm-options),
[Node Buffer views](https://nodejs.org/api/buffer.html#buffers-and-typedarrays),
[Rust Arc](https://doc.rust-lang.org/std/sync/struct.Arc.html),
[ReadOnlySpan](https://learn.microsoft.com/en-us/dotnet/api/system.readonlyspan-1?view=net-10.0),
[Swift Crypto](https://github.com/apple/swift-crypto), and
[Erlang crypto](https://www.erlang.org/doc/apps/crypto/crypto.html#hash/2).
The ownership conclusions are engineering inferences from those documented data
models, not claims that the alternative languages cannot implement safe binding.

`hash-probe.mjs` checks empty/abc SHA-256 vectors, four distinct 1 MiB payloads,
and a mutable alias versus an owned-copy control. `measure_binding.py` evaluates
the production API with the same four payloads at its 4 MiB aggregate ceiling.
Digests match across the native implementations; Node's alias changes while its
owned snapshot remains unchanged. Python reports four matched references and no
physical qualification. The full artifact suite separately checks tampering,
missing/extra payloads, type/size bounds and preservation of calibration failures.

Ten production verification calls measured median 4.058 ms and maximum 58.344 ms;
single-call traced allocations peaked at 10,949 bytes, excluding the preallocated
4 MiB input. The active hash object came from `_hashlib`. Node's copy-and-hash
probe and Python's complete verifier do different work, and this shared host is
noisy: **the retained timing arrays are not a cross-language ranking**. Neither
probe changes cryptographic or physical assurance. Results and source hashes are
in `hash-node-result-v1.json` and `binding-python-result-v1.json`.

**Decision: KEEP Python for artifact byte binding.** Its immutable byte boundary,
explicit budget checks, mapping snapshot and native SHA-256 meet the requirement
without extra payload copies or another execution/crypto dependency. The measured
allocation envelope and finite contract tests support this choice. Native Rust
ownership and Erlang immutable binaries are viable, but no stronger property
required by this API remains unimplemented, and no measured bottleneck calls for
a new boundary. This is not a preference for interpreter hashing: the actual
hashing is native. Reopen for a native consumer ABI, concurrent producer contract,
or a demonstrated throughput/memory requirement the current path cannot satisfy.
No winning production migration is identified.

## Campaign coverage: constraints and alternatives

The offline API accepts at most sixteen cases and sixty-four attempts, with each
manifest capped at 65,536 bytes. It has no durable database, policy distribution,
concurrent writers, external query API or embedded-device requirement. Every
attempt contributes to the commitment and every negative finding survives even
when another attempt meets the case minimum. A repeated digest invalidates all
occurrences globally, including across cases. Missing cases count as zero.
Reports retain plan order, sort findings and commit exact submitted bytes and
evaluation instants independently of submission order. Fixed errors and aggregate
reports must not disclose private case names. No hard execution deadline exists.

Candidate discovery for these aggregation requirements includes:

| Candidate | Decisive property and remaining work |
|---|---|
| Python Counter, sets and ordered lists | Explicit multiset counting before admission; no database or policy interpreter; bounded exact integers and deterministic explicit sorting. |
| SQL/SQLite in memory | GROUP BY, COUNT and LEFT JOIN directly express duplicates and absent coverage. Preserve a distinct ordinal per submission, use bound parameters, close the connection, and retain negative rows separately. |
| OPA/Rego | Declarative decisions over structured documents and denial sets fit coverage rules. Undefined decisions must fail closed; retain array indices so set construction cannot erase duplicate attempts; strict byte ingress and commitments still need a host boundary. |
| Soufflé/Datalog | Relational aggregation suits evidence coverage and larger derived relations. An attempt ordinal is necessary to preserve multiplicity; facts/imports and fixed report serialization require a host boundary. No recursive relation is required here. |
| CUE comprehensions and constraints | Good fit for plan shape and per-case constraints. Global multiplicity, retention of all rejected attempts, raw-byte commitments and report construction still require explicit design; schema validation alone is not the complete evaluator. |

Sources inspected 2026-10-10: [Python multiset counting](https://docs.python.org/3/library/collections.html#collections.Counter),
[SQLite aggregation](https://www.sqlite.org/lang_aggfunc.html),
[private in-memory databases](https://www.sqlite.org/inmemorydb.html),
[Rego policy semantics](https://www.openpolicyagent.org/docs/policy-language),
[Soufflé aggregates](https://souffle-lang.github.io/aggregates), and
[CUE comprehensions](https://cuelang.org/docs/tour/expressions/listcomp/).
The suitability judgments are engineering inferences from these documented
features, rather than measured claims about unimplemented alternatives.

### Executable relational comparison

`campaign_sql.py` is an audit-only SQL implementation of aggregation and report
construction. It deliberately shares strict plan/input admission and per-capture
semantic findings with production; it is **not** an independent whole validator.
The SQL path inserts every submission with its ordinal, groups digests before
counting eligible rows, uses a left join for missing coverage and orders all
commitment rows. It creates a private `:memory:` connection, requests memory-only
temporary storage, binds all input values as parameters, and explicitly closes
it. No files, SQL supplied by a caller, extension loading or network are used.

The new test class first failed eleven methods because the prototype did not
exist. After implementation, all eleven methods pass across 48 candidate calls,
including the original nine contract methods plus permutation and full-cardinality
cases. Assertions cover fixed errors, timing/rig/environment negatives, missing
coverage, cross-case duplicates, commitments and permanently false qualification
flags. Changing the SQL singleton filter from `n = 1` to `n >= 1` causes three
assertion failures and zero execution errors. The mutation is temporary and never
changes production. This demonstrates sensitivity to accidental duplicate credit.

`compare_campaign.py` reproduces those checks and runs ten alternating-order calls
of each full path at sixteen cases and sixty-four unique byte inputs. Python
3.13.5/SQLite 3.46.1 measured medians of 86.502 ms (Python aggregation) and 87.162 ms
(SQL aggregation), with maxima 91.679 ms and 90.344 ms. The small median difference
on this shared host is **not** a speed ranking. Tracemalloc peaks were 37,823 and
48,866 bytes respectively; preconstructed inputs and native SQLite allocations
are excluded, so these numbers are not total memory comparisons. Source digests,
raw timing arrays and the report are retained in `campaign-sql-result-v1.json`.
Whitespace-distinct synthetic manifests exercise the byte-identity contract only;
they do not establish independent physical captures.

**Decision: KEEP Python for campaign coverage.** The required operation is a
finite multiset count and negative-finding union, with deterministic formatting.
Counter and sets express it directly without query schema, connection lifetime,
fact import or undefined-policy-result semantics in the trusted production path.
The relational alternative demonstrates contract parity, but no correctness or
measured resource improvement that warrants adding its execution boundary at
64 rows. Rego/CUE/Datalog would become stronger candidates if externally authored
policies or recursive relationships were required; SQL would gain value for
large persistent evidence collections. Those are absent deployment requirements,
not objections to the technologies. Existing language, installation convenience
and rewrite cost do not decide this choice. No winning migration is identified;
the executable alternative and mutation checks remain regression evidence.

Reproduce with `python3 -m qualification.technology.compare_campaign`.
Hosted qualification contracts run the candidate parity tests on Python 3.9 and
3.13; the audit job retains the comparison artifact. Workflow configuration does
not constitute a hosted pass.

Cursor: CLI/report delivery and verification tooling. No lane audit completion
marker is warranted.
