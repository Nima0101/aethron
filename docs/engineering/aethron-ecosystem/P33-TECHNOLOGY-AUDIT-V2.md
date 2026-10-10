# P3.3 retrospective technology reassessment, policy 2

Review baseline: `20d54aeaaca1d20078112335d5dd12a2d5acdcc3`.
This supersedes earlier technology-selection notes for the components reviewed
below. It is an incomplete audit, not a P3.3 or P12 completion claim.

## Inventory and cursor

Review the original client boundary before its later lifecycle changes. The
substantial implemented P3.3 surface is `examples/clients/typescript`: generated
API types/schema, runtime validation, observation projection, HTTP/SSE lifecycle,
and packed distribution with synthetic fixtures. No separate Android/JVM client,
desktop launcher, or P12 scene/map/mission/replay application was found at this
baseline. Their absence is outstanding software work, not an external gate.

| Component, in dependency/history order | Policy-2 status |
| --- | --- |
| Versioned contract consumption and runtime admission | MIGRATE to generated AJV validators; executable evidence below |
| Observation ownership, clocks and projection | KEEP TypeScript/host clock; MIGRATE ordinary fields/full scene to native private fields/minimal projection; evidence below |
| Authenticated stream/session/renderer lifecycle | In progress: migrate ingress framing/JSON admission; HTTP/session/cleanup decisions and producer size reconciliation remain |
| Package distribution and contract fixture tooling | Pending reassessment; migration package verification below is a regression check |

P1.5 supplies `scripts/edge_generate_types.py`, `scripts/edge_node_e2e.py` and
`integrations/edge/aethron_edge/client.py`. They are shared foundation interfaces,
not new implementations owned exclusively by this lane. Their policy-2 producer
audit must be reconciled with the foundation lane; no competing generator or
Python observer was created here. The web camera detector is not a P12 operator
application. Appliance supervision/provisioning belongs to its producing lanes.
These boundaries do not certify those components or exempt their consumers from
the remaining audit.

## First component: contract consumption and runtime admission

Constraints: an installable Node 22 ESM client with TypeScript declarations must
accept untrusted JavaScript values against the existing API-v1 JSON Schema,
including strict additional-property rejection, finite numbers, bounded integers,
enums and Unicode lengths. Admission must not coerce or mutate input. Preserve
scene/health/gap semantics and UNKNOWN current state. No native device API,
heavy numerical kernel or real-time qualification is involved. Startup memory,
dynamic-code exposure, interoperable packaging and reproducibility matter.

The language search included credible source-to-JavaScript and WebAssembly
ecosystems, not just installed compilers. Primary documentation consulted
2026-10-10:

| Candidate | Decisive properties for this boundary |
| --- | --- |
| TypeScript / native ECMAScript | [Declarations describe the JS package interface](https://www.typescriptlang.org/docs/handbook/declaration-files/introduction.html). They do not validate incoming values. Generated JS validators directly consume JS objects and can run under the host's dynamic-code restriction. |
| ReScript | [genType exports values and types to JS/TS](https://www.rescript-lang.org/syntax-lookup/decorator_gentype/). Its stronger internal types are credible, but external unknown JSON still requires a decoder or schema-validator binding. No demonstrated improvement in the versioned admission decisions. |
| Kotlin/JS | [JS export and type mappings](https://kotlinlang.org/docs/js-to-kotlin-interop.html) make JS library delivery feasible. Export restrictions and JS interop remain part of the boundary; internal Kotlin types alone do not check arbitrary JS objects. No JVM/Android code is shared by this implemented component. |
| Dart compiled to JS | [Static JS interop declarations](https://dart.dev/interop/js-interop/usage) support host integration. This boundary would still require runtime schema admission plus an exported JS interface; no measured numerical workload favors the extra compilation layer here. |
| Rust / WebAssembly | [Reference types reduce JS/Wasm glue](https://wasm-bindgen.github.io/wasm-bindgen/reference/reference-types.html). Native memory guarantees are useful for native kernels; this client receives JS values and uses host networking. Either schema validation stays in JS or moves across an additional data boundary. No native kernel advantage is established for this component. |

Decision: **KEEP TypeScript/ECMAScript for the public boundary; MIGRATE validation
from import-time compilation to generated validators.** This is based on direct
host-value admission, schema fidelity and the measured runtime strategy below,
not compiler availability or rewrite cost. Other-language prototypes were not
executed; no comparative speed/memory ranking of those languages is claimed.
Revisit if a required native kernel or shared JVM implementation changes the
constraints. Pending components must receive their own decisions.

[AJV standalone generation](https://ajv.js.org/standalone.html) supports compiling
schemas during builds and avoids runtime Function construction. The production
build now generates CJS validators and the ESM client imports them. Keep strict
AJV 8.20.0 and the exact schema; no alternate handwritten schema or type-only
decoder is introduced. CJS accommodates the generated Unicode-length `require`
helper. AJV therefore remains a runtime dependency. The generated module adds
74,916 uncompressed bytes; this migration does not claim a dependency-free or
smaller package.

## Executable evidence and limitations

The pre-migration client failed to import under
`--disallow-code-generation-from-strings`; the migrated client passes. All 35
observation/transport regressions also run with that restriction. The additional
validation tests compare both old and new validators on 682 cases, including
nested deletions/replacements, non-finite numbers, unknown fields and Unicode
boundaries. Input mutation is checked. A deterministic regeneration comparison
binds built code to the bundled schema. This is same-compiler migration parity,
not an independent proof that the upstream schema captures all safety semantics.

`node audit-validation.mjs` executes three sequential cold processes per strategy,
alternates order and performs 10,000 alternating valid/invalid scene validations
per process. The median validator-ready interval fell from 1,859.77 ms to
110.95 ms on the shared Linux Node 22.23.2 host; raw results include RSS deltas
and warm-loop timings. The clock excludes process launch and fixture setup.
Scheduling pressure makes these observations unsuitable as frozen thresholds or
platform-performance claims. Dynamic-code exclusion and unchanged admission are
the decisive checks. Source hashes and all results are in the
[evidence record](evidence/phase3/p33-validation-audit-v2.json).

Retained failures: the original dynamic-code import failure; a test authoring
error that applied the track-ID length constraint to `reasons` (both validators
agreed; corrected test, unchanged schema); host thread-allocation failures during
the first combined verification/probe attempt; and an initial npm pack failure
using the read-only default cache. Focused checks were rerun sequentially with
bounded Node resources and a workspace cache. No full repository, VM, Docker,
device, browser or live-server qualification is claimed.

## Second component: observation ownership, clocks and projection

Baseline: `bb36aafed2e90e271dc46935c9f2f1b888dd8172`. Requirements are a synchronous
Node/JavaScript class, runtime isolation of admitted state from caller property
writes, finite nonnegative local fractional milliseconds, irreversible expiry
and rollback clearing, independent output arrays, and no unnecessary identifiers
retained by the display object. Preserve the inclusive wire lease and UNKNOWN
current state. The work is bounded projection of at most 32 tracks, without
native hardware or a numerical kernel. A foreign runtime would still need an
explicit JS value and clock boundary.

The timing source must remain local. [High Resolution Time](https://www.w3.org/TR/hr-time-3/)
distinguishes a monotonic clock from adjustable wall time and warns that timer
callbacks may be throttled. Rendering checks elapsed time itself. Explicit clock
arguments remain a trusted integration/testing input, not a freshness proof.
No OS-suspend, browser scheduling or hard-real-time guarantee follows from these
tests. A queued callback cannot promise immediate clearing while JS is suspended.

Candidates researched 2026-10-10:

| Candidate | Decisive comparison |
| --- | --- |
| TypeScript ordinary `private` fields | [TypeScript documents that these are not runtime-private](https://www.typescriptlang.org/docs/handbook/2/classes.html). Executed property-write and reflection counterexamples reject this representation. |
| ECMAScript native private fields | Same reference supports runtime privacy for `#` fields. Node's supported target emits these directly. This preserves the exported class/prototype interface with shared methods; admission and output copying remain explicit. |
| ECMAScript closure or WeakMap storage | Both hide state from ordinary properties. The executed closure candidate passes the trace and collision checks, but allocates per-instance methods and changes the direct class/prototype model. WeakMap would preserve shared methods with external storage; it adds a separate lookup/store without an established need at this target. |
| ReScript | [Immutable bindings and explicit mutable references](https://rescript-lang.org/docs/manual/latest/mutation) can describe the state machine clearly. A record/ref exported into JavaScript is not by itself the required runtime boundary; a hidden closure/module boundary and copy-out are still needed. No stronger runtime guarantee over the executed host primitives was established. |
| Kotlin/JS | [Monotonic time sources](https://kotlinlang.org/docs/time-measurement.html) are platform-specific: Node uses `process.hrtime`, while browser fallback can use wall time. A migration must pin the clock and JS export semantics, not assume the abstraction proves freshness. Cross-platform duration types offer no demonstrated benefit for this single-host millisecond contract. |
| Dart/JS | [Library privacy](https://dart.dev/language/libraries) and [Stopwatch](https://api.dart.dev/dart-core/Stopwatch-class.html) are credible ownership/time tools. Node-facing JS interop still requires an explicit exported boundary and unit conversion. No Dart platform code or duration arithmetic is required by this component. |

Decision: **KEEP TypeScript and the local host monotonic clock; MIGRATE the state
representation to native private fields holding only the display projection.**
The decision rests on runtime encapsulation, minimal retained data and the
existing class contract, not compiler availability. Alternative-language emitted
artifacts were not measured and are not ranked by speed. Host closure storage is
a viable alternative; the benchmark actually favored it for this small workload.
It did not establish a resource constraint requiring the class/API adaptation.

Before implementation, 35 client cases passed and four new regressions failed:
reflection disclosed the handle, a public `received` property extended expiry,
a public `scene` property replaced validated state, and a throwing input getter
left a reentrant observation active. After migration all 39 pass. Clone/validation
failure now clears state again before returning the fixed `invalid_event` error.
The projection contains only observed state, distinct sources, covariance and
lease duration; two private local timestamps complete the state. Input cloning
and returned-array copying remain. Private fields do not sandbox arbitrary code
running in the same process or guarantee physical memory zeroization.

`audit-observation.mjs` retains a JS transcription of the baseline and a closure
candidate solely for the audit. All three match across 45 deterministic traces
and 162 views, including exact/fractional expiry, rollback, non-finite clocks,
input mutation and disconnect. Four intentional ownership corrections are
covered separately. The `--check` path is part of `npm test` and skips timings.
The bounded probe runs three rounds, each with 100 accepts and 2,000 views of
32 synthetic tracks. Median totals were 173.10 ms (legacy), 30.12 ms (closure),
and 91.00 ms (native private projection). This combined strategy comparison runs
in one process on a shared host; JIT/order effects remain. It neither isolates
private-field access cost nor establishes portable performance thresholds.
Raw measurements, hashes, failures and package verification are in the
[observation audit record](evidence/phase3/p33-observation-audit-v2.json).

The next cursor is authenticated stream/session/renderer lifecycle. Distribution
and shared producer reconciliation also remain; no audit completion is claimed.

## Third component, ingress slice: stream framing and JSON admission

Baseline `30895273dfa0260e9e3a5a59c631b46f6d03ada2`. Requirements derive from
[API-v1](API-CONTRACT.md): bearer headers, no persisted event history or automatic
replay, ordered session-bound scene/control events, bounded UTF-8 JSON, unique
keys, and fixed errors without input echo. The consumer is a Node ESM package;
native OS networking is not required. Fetch chunk boundaries are not event
boundaries. Current-state UNKNOWN and independent render-time expiry remain.

Current primary-source comparison (2026-10-10):

| Candidate | Decisive property for this deployment |
| --- | --- |
| Native EventSource | The [standard constructor and reconnection behavior](https://html.spec.whatwg.org/multipage/server-sent-events.html) do not provide this client's arbitrary bearer-header option and introduce reconnect/history semantics requiring a separate integration. Token URLs are excluded by the contract. |
| Fetch + `eventsource-parser` | Its [implementation](https://github.com/rexxars/eventsource-parser/blob/main/src/parse.ts) handles general SSE framing, but the buffer guard measures string characters, not complete raw event bytes; JSON duplicate-key admission is outside its purpose. A byte-bound and strict JSON adapter would still be necessary. No library defect is claimed from these differing requirements. |
| Kotlin/Ktor | [Client SSE](https://ktor.io/docs/client-server-sent-events.html) provides coroutine sessions, header configuration and deserialization. The exact wire byte cap, duplicate-key handling and no-history policy still need explicit adapters. A JVM runtime or Kotlin/JS export adds a deployment boundary without replacing these guards in the Node client. |
| Dart HTTP streaming | [HttpClient](https://api.dart.dev/dart-io/HttpClient-class.html) and [request abort](https://api.dart.dev/dart-io/HttpClientRequest/abort.html) provide a credible native streaming lifecycle. They do not directly deliver the Node module interface or the strict AETHRON wire admission layer. |
| C eventsource client | [eventsource-c](https://github.com/rexxars/eventsource-c) exposes bounded parser buffers and incremental polling, a credible embedded choice. A native bridge and lifetime rules would be required for this JS package; there is no demonstrated embedded/network bottleneck to justify that boundary. |
| TypeScript + host fetch + bounded profile decoder | Direct header/cancellation integration, one reusable fixed byte buffer, strict object preflight and native JSON grammar validation satisfy the measured ingress requirements without another runtime. Explicitly limited to the published producer profile plus CRLF/multiline interoperability, not arbitrary SSE. |

Decision for this slice: **KEEP TypeScript/fetch; MIGRATE concatenated decoded
chunks to a bounded incremental wire decoder and duplicate-aware JSON preflight.**
Language choice follows the deployment interface and byte-admission requirements;
alternative compilers were not benchmarked or rejected for being unavailable.
The narrow decoder has a maintenance cost: its supported profile is explicit and
its lexical/framing boundaries have executable tests. General SSE packages remain
preferable if requirements later expand to general EventSource semantics.

Twelve focused regressions failed before implementation: a large fetch chunk
containing many valid events was rejected, CRLF and multiline data were mishandled,
UTF-8 size was undercounted, duplicate root/escaped/nested keys were lost, named
event mismatch and a second data object were ignored, partial input was discarded,
and malformed JSON echoed a private marker in its error. All twelve pass after
migration. Additional cases freeze the inclusive 65,536-byte raw event boundary,
the producer mismatch below, and 36 valid lexical/chunk combinations plus invalid
grammar, depth, UTF-8 and history-field cases. No large fuzz run is claimed.

A further regression failed after the initial decoder migration: malformed input
could leave the last projection admitted while `reader.cancel()` was pending.
The client now clears the projection and decoder before awaiting cancellation;
the deterministic watchdog test passes. This does not yet bound cancellation
completion or guarantee the subsequent DELETE when cancellation never settles.

`WireDecoder` retains at most one 65,536-byte wire buffer, processes each byte once
for framing, and parses only complete LF/CRLF events. It zeroes the used buffer on
dispatch and cleanup. This does not bound upstream fetch allocations or claim
physical memory erasure. A depth-eight lexical preflight detects decoded duplicate
keys before native JSON parsing; native parsing still validates grammar and AJV
still validates the resulting schema. Comments are inert; event names, when
present, must match JSON kind. Existing unnamed data-only clients remain accepted.
Bare-CR, BOM-prefixed framing, ID/retry fields and incomplete events are rejected.

Retained negative evidence: `service/events.py` currently caps JSON payload bytes,
whereas API-v1 says 64 KiB per event. A synthetic 65,536-byte JSON payload passes
that producer size calculation but exceeds the client's complete-wire-event cap.
The fixture explicitly expects rejection, not interoperability success. This is
handed to the producing foundation lane; no peer code or frozen limit was changed.
The transport audit cursor remains open for that reconciliation and for HTTP
response/session/cleanup admission. In particular, this slice does not claim
lexical integer-form enforcement, bounded session-response parsing, general SSE
compliance, live-server qualification or completed client security review.

Source-bound regression and package results are retained in the
[ingress evidence](evidence/phase3/p33-stream-ingress-audit-v2.json). Earlier negative
evidence remains unchanged. There is still no audit-complete marker.
