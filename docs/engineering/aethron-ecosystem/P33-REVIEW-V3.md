# P3.3 client review, revision 3

Baseline: `0310a092bf45334f1b94ae2855ef032d3705073c`, including the pending
cancellation correction. This starts a fresh review; earlier audit evidence is
retained and does not establish completion. Scope is the read-only Node client
and its distribution boundary. No iOS implementation is included.

## First component: generated contract admission

Requirements: consume the versioned JSON schema without coercion or hidden
mutation; reject unsupported fields, unsafe numeric values and false authority;
provide a Node ESM interface and TypeScript declarations; avoid runtime schema
compilation. Neither schema admission nor a bearer token attests sensor accuracy,
transit freshness, a deployment authorization policy or hardware qualification.

Reviewed generator, bundled schema, declarations, package configuration and
validation tests. Current source research (2026-10-10) revisits the candidate set:

| Candidate | Evidence and decision for this component |
| --- | --- |
| TypeScript/ECMAScript with generated AJV | [Standalone generation](https://ajv.js.org/standalone.html) separates compilation from runtime validation. The current build demonstrably produces identical validators and imports with string code generation disabled. KEEP. |
| ReScript | [JSON decoding](https://rescript-lang.org/docs/manual/latest/json) provides explicit typed boundary handling. For this schema-owned contract a handwritten decoder would add a second definition; binding the same generated validator would preserve the existing runtime mechanism. No additional internal state machine in this component benefits from that change. |
| Kotlin/JS | [JavaScript exports and type mapping](https://kotlinlang.org/docs/js-to-kotlin-interop.html) make it a credible library implementation. Exported static types still require runtime admission, and no shared Kotlin domain implementation is present here. It offers no demonstrated replacement for schema validation. |
| Dart/JS | [Host interop](https://dart.dev/interop/js-interop/usage) supports a compiled client, but external declarations are not the versioned schema's runtime validator. An additional JS interface would still be needed for the selected public package contract. |

**KEEP the language and generated-validator strategy; FIX the evidence gap.**
The earlier 682-case test compares two implementations using the same AJV engine.
That establishes migration parity, not independent correctness. Fourteen new
explicit negative cases now reject authority escalation, identity/embedding
fields, prediction-as-evidence, nonfinite covariance, unsafe/boolean counters,
lease overflow/coercion, extra tracks and PRESENT health messages. Both checks
are retained. No foreign-runtime speed ranking is claimed. Current decisive
properties are direct host-value validation and one authoritative schema, not
installed tooling or familiarity. No new production migration is justified by
these checks.

The current source and tests contain no actuator transport. This consumer exposes
UNKNOWN current state and does not provide a command interface. Its checks are
not MLS, CNSA, DDS, hard-real-time, five-nines, or tactical deployment certification.
Any such downstream interpretation is unsupported. The producer owns changes to
its versioned schema; this review does not rewrite that peer interface.

## Review cursor and pending work

| Owned surface | Fresh review status |
| --- | --- |
| Generated contract admission | Reviewed above and in numeric slice; 5 validation tests pass, including 14 independent negative cases |
| Observation projection and local clocks | Reviewed below; host-clock exception correction and claim clarification |
| HTTP/session/stream/renderer lifecycle | Reviewed in the third-component slices below; bounded admission, cancellation, redirect, error and numeric corrections retained; producer SSE-size reconciliation remains open |
| Package distribution and fixtures | Manifest, generator, installed declarations and service smoke reviewed below; offline removal/reinstall coverage added; cross-version upgrade remains unverified |
| Android/JVM, desktop lifecycle, P12 operator application | Fresh file inventory found no owned implementation; platform selection and implementation remain executable work |

No completion marker is created. The session-response admission slice below
resolves the previously open response limit. Integer wire forms are corrected in
the numeric slice. Producer whole-event versus payload-size reconciliation remains open. Cancellation no longer blocks DELETE, but a source may ignore
cancellation and a remote server may fail to delete its session. Full live-server,
platform and deployment qualification are not established by synthetic tests.


## Second component: observation ownership and local clocks

Baseline `0056d221c954a62570016948e2435cc681466607`. Re-read the projection,
cloning, timestamp, disconnect and returned-array paths. Requirements remain
bounded-schema read-only display state, no retained transport/track identity,
no revival after an invalid render sample, and UNKNOWN current state. A local
lease is not proof of sensor freshness or remote time synchronization.

Current source comparison revisits the language and storage choice:

| Candidate | Decisive property for this component |
| --- | --- |
| Native JavaScript private fields / TypeScript | [Runtime private fields](https://www.typescriptlang.org/docs/handbook/2/classes.html) protect this small projection from ordinary property collisions. No native numeric kernel or OS I/O is involved. |
| JavaScript closure storage / ReScript compilation | Lexical encapsulation is credible; the retained closure probe was faster than the class in its combined workload. That is not a correctness or isolation distinction and no measured latency requirement mandates replacing the public class. ReScript can use the same host clock and lexical model; changing source language would not supply a different clock trust boundary. |
| Kotlin | [Time measurement](https://kotlinlang.org/docs/time-measurement.html) provides monotonic time abstractions with platform-specific implementations. A Kotlin/JS version still depends on its host clock; native/JVM deployment would be a different client boundary. |
| Dart | [Stopwatch](https://api.dart.dev/dart-core/Stopwatch-class.html) provides elapsed ticks and durations. It does not attest remote freshness or preempt a stalled host callback. A compiled JS wrapper still needs the public object's admission/ownership rules. |

**KEEP TypeScript, native private projection and local monotonic time; FIX clock
read failure handling; CLARIFY lifecycle/privacy claims.** [High Resolution Time](https://www.w3.org/TR/hr-time-3/)
describes monotonic timestamps separately from callback scheduling and clock
origins. Neither selecting a different compiler nor switching to wall time cures
an unavailable clock. A small guarded clock read maps exceptions to the existing
invalid-sample clearing path. It adds no clock fallback, extrapolation, new lease
or performance claim. Two new regressions failed on the baseline and pass after
the correction: host clock exceptions during acceptance and rendering no longer
expose the source error or leave an old observation available to a recovered clock.

Previous private-state, fractional-boundary, rollback and copying tests remain.
The deterministic legacy/closure/current comparison is rerun for behavioral
parity only; earlier shared-host timings are retained, not relabeled as fresh
measurements. Alternative compilers were not benchmarked, and there is no claim
that TypeScript is universally faster or provides process isolation.

The README now distinguishes a requested 20ms check interval from actual callback
delivery, internal clearing from revocation of already-returned snapshots, and
identifier omission from anonymity. Direct object acceptance clones before schema
validation, so it does not have the wire decoder's pre-parse byte allocation bound.
Arbitrary in-process code, suspension, host clock rate and scheduler correctness
remain outside this object's guarantees. No hard-real-time or physical qualification
is inferred. The next earliest component is the full HTTP/session/stream lifecycle;
its known session-response and lexical-number issues remain unresolved.

## Third component, session-response admission slice

Baseline `57e9b3998d8a63a5839a27cc51bccf1162961122`. The previous path used
`Response.json()` and checked only a returned handle regex. It accepted missing,
extra, duplicated or mismatched profile fields and accumulated an unrestricted
body before parsing; malformed JSON and read failures could expose source errors.
The existing published `SessionHandle` schema requires exactly `session` and
`source_profile`; the local producer already emits both. This correction consumes
that schema without modifying peer code.

Requirements are defensive admission of one small authenticated HTTP response,
fixed errors, exact profile binding and no use of an unvalidated handle. The
client now caps its own body accumulator at 65,536 bytes before decode/parse.
This is an explicit local admission policy, not a newly asserted server response
limit. Fetch may allocate larger chunks upstream; no total-process/network
memory bound is claimed. A stalled response still needs caller cancellation,
and a source ignoring cancellation may retain its own resources.

Current primary-source comparison (2026-10-10):

| Candidate | Decisive property |
| --- | --- |
| Fetch `Response.json()` | The [body consumption algorithm](https://fetch.spec.whatwg.org/#dom-body-json) consumes the body before JSON conversion; this API has no caller-supplied byte cap or duplicate-key rejection policy. It does not meet this boundary unaided. |
| TypeScript/host reader + generated schema | The host reader allows checking each chunk before copying into the fixed buffer. [AJV standalone generation](https://ajv.js.org/standalone.html) can add the existing session schema without runtime compilation. The already-tested duplicate/depth preflight can be shared. |
| Kotlin/Ktor | [Response handling](https://ktor.io/docs/client-responses.html) supports streaming as well as complete-body conversions; explicit byte accounting and contract admission are still required. A Kotlin client is credible, but it does not itself replace these protocol guards in the Node module. |
| Dart HTTP | [HttpClientResponse](https://api.dart.dev/dart-io/HttpClientResponse-class.html) is a byte stream with response metadata. A Dart implementation could enforce the same guards, but would need a separate host/module boundary and schema integration for this Node distribution. No throughput requirement or measured runtime advantage justifies that change here. |

**KEEP TypeScript/fetch and build-time schema generation; FIX body admission.**
A dedicated internal helper accounts for bytes, decodes UTF-8 strictly, rejects
duplicate/deep/invalid JSON, validates the generated `SessionHandle`, and binds
its profile to the request. All body/schema failures return `invalid_session`.
Cleanup clears the accumulator and releases the reader without awaiting source
cancellation. No body/error value is logged or persisted. No command interface,
actuator channel or new dependency is added.

Sixteen focused cases include thirteen baseline failures: missing/wrong/extra
fields, duplicate and escaped keys, malformed private input, null body/root, BOM,
oversize response, reader cleanup and raw transport errors. Positive controls
include split one-byte input and the inclusive local byte limit. Existing client
fixtures previously omitted the required profile and are corrected to match the
producer; this is not a server schema change. Invalid replies produce no further
handle-based requests. Consequently, an invalid or lost response cannot establish
that a remotely created viewer handle was released; no remote-cleanup guarantee
is made.

The full transport review remains open for request/redirect policy, cancellation
across all response phases, lexical integer forms and the known producer raw-event
size mismatch. Neither this slice nor earlier tests establish deployment security,
physical freshness or hard-real-time behavior. Review evidence is in
[the session record](evidence/phase3/p33-session-review-v3.json).

## Third component, authenticated HTTP redirect slice

Baseline `ecd3991d2aef42c0f787378a06a66fc31ec1fa00`. Earlier generated admission
was rerun (4 tests, including the independent safety negatives); observation,
session and stream regression checks remain part of this slice's verification.
Requirements are one caller-selected read-only service endpoint, no implicit
forwarding of authenticated requests, preservation of session cleanup, Node ESM
integration, and no browser or target-device qualification claim.

The default fetch redirect policy followed responses for POST, GET and DELETE.
Thirty real loopback HTTP controls reproduced follow-up requests at unintended
destinations (five redirect statuses, three request phases, same/different origin).
Same-origin destinations received the synthetic bearer token. Cross-origin native
fetch stripped authorization in these tests, but still sent a request; that does
not meet the explicit no-redirect policy. This finding is not a claim of token
forwarding across origins.

Current official-source comparison (2026-10-10):

| Candidate | Decisive property |
| --- | --- |
| TypeScript with host fetch | [Fetch HTTP redirect handling](https://fetch.spec.whatwg.org/#http-fetch) supports redirect mode `error` before following. The Node interface exposes it directly for every existing request. |
| Kotlin/Ktor | [Redirect controls](https://ktor.io/docs/client-redirect.html) allow disabling following. A JVM/client migration could enforce the same policy but provides no additional endpoint authorization property; Node module consumption would require a different distribution boundary. |
| Dart HTTP | [HttpClientRequest redirect controls](https://api.dart.dev/dart-io/HttpClientRequest/followRedirects.html) can disable following, with documented method/header rules. A Dart implementation is credible for a Dart client, but redirect security here does not require a different runtime. |
| Manual redirect validation | Explicit host redirect refusal avoids parsing and authorizing a second destination or replaying request bodies. No requirement permits endpoint migration, so a hand-built redirect resolver would add unnecessary authority decisions. |

**KEEP TypeScript/host fetch; FIX all three requests to reject redirects.** No
runtime ranking or foreign-runtime benchmark is claimed. Direct host policy is
the decisive property, verified through actual native fetch and loopback sockets,
not fetch mocks. Thirty retained baseline assertion failures become passing;
one nonredirected positive control still creates, reads and deletes the session.
Rejected GET redirects still clear the display and attempt DELETE at the original
endpoint. DELETE redirect refusal remains best effort; it is not a deletion receipt.
The README also corrects the unconditional claim that abort releases a handle.

This does not validate the caller's initial base URL, attest TLS configuration,
restrict DNS/proxies, normalize all native fetch exceptions, or bound all response
cleanup phases. Those remain in the earliest open transport review, along with
lexical integer forms and producer payload/wire-size reconciliation. No new
command, hardware, identity or authority surface is introduced. The parent review
and lane are incomplete. Evidence is recorded in
[the redirect record](evidence/phase3/p33-redirect-review-v3.json).

## Third component, unused HTTP response ownership slice

Baseline `d1f927461ecacae72b3bb36176c1d223caaf98a0`. The earliest generated
admission, projection and clock controls were rerun with the transport suite.
The review found no explicit disposal of failed POST/GET bodies or DELETE replies.
Native GET already received cancellation through the existing event abort in
`finally`; that passing negative-evidence control is retained. Native POST and
DELETE with no response EOF remained open beyond observer completion on baseline.
Eight controlled-source cases additionally expose omitted body cancellation and
exercise pending/rejected cleanup without relying on socket timing.

Requirements: release interest in unused untrusted response bytes, avoid complete
body buffering or an unbounded drain, preserve the original error/success result,
and avoid delaying session cleanup on an arbitrary source promise. Node ESM,
existing authenticated fetch routes and the public API remain the deployment
boundary. There is no real-time, remote-deletion or upstream allocation guarantee.

Current primary-source comparison (2026-10-10):

| Candidate | Decisive property |
| --- | --- |
| TypeScript/native fetch with explicit cancellation | [Undici guidance](https://github.com/nodejs/undici#garbage-collection) calls for consuming or cancelling bodies rather than relying on garbage collection. [Streams cancellation](https://streams.spec.whatwg.org/#rs-cancel) expresses lost interest and invokes the source cleanup mechanism. The host API already supplies the required operation. |
| Complete-body read or drain to EOF | A streaming or buffered drain still depends on EOF from an untrusted peer. The no-EOF fixtures make it unsuitable for bodies this client does not need. No parse or retained payload is necessary here. |
| Kotlin/Ktor | [Scoped response streaming](https://ktor.io/docs/client-responses.html#streaming) makes resource ownership explicit. A separate Kotlin client is credible, but it still needs cancellation/error policy and would change this Node distribution boundary without a demonstrated resource or latency advantage. |
| Dart streams | [Subscription cancellation](https://api.dart.dev/dart-async/StreamSubscription/cancel.html) separates stopping events from the future reporting resource cleanup. It still requires a decision about pending/rejected cleanup; selecting Dart alone would not remove that responsibility. |

**KEEP TypeScript/native fetch; FIX unused response disposal.** The helper invokes
body cancellation where there is no reader and observes rejection without waiting.
Existing reader-owned cancellation paths are unchanged. No body logging, buffering,
retry, schema change, authority or runtime dependency is added. All original
session/stream errors and best-effort DELETE behavior are preserved.

Fourteen controls pass after correction: eight controlled-source cases, three
null-body controls, and three actual native-fetch loopback cases. The corrected
baseline has ten assertion failures and four passes. The initial test incorrectly
used a null successful GET body in a DELETE fixture; that run is retained, and
only that fixture was corrected before the production edit. The native one-second
check is a bounded regression timeout chosen below the request-abort deadlines;
it is not a deployment performance claim. Socket tests complement controlled
streams, which independently detect awaiting or losing the cleanup promise.

Parent transport review remains open for initial endpoint trust, native fetch
error disclosure, caller abort across all phases, and the lexical-number and
producer event-cap issues. Distribution/tooling and the remaining client inventory
have not completed V3 review. No completion marker is created. Source/report/artifact
bindings are in [the disposal record](evidence/phase3/p33-disposal-review-v3.json).


## Third component, transport exception and caller cancellation slice

Baseline `78e8cd98ffef6e5c7a0aac2a03b5669ae87676b1`. Fresh earliest admission,
projection and clock controls remain passing in the combined source run. This
slice found raw POST/GET/read rejection values escaping the observer, including
private custom abort reasons. It also found that aborting inside a display callback
still processed further events in the same chunk, or parsed a malformed tail and
replaced cancellation with an admission error. Session body errors already had
fixed diagnostics; that passing baseline is retained.

Deployment constraints: Node ESM client, native fetch/ReadableStream, synchronous
application callback, strict ingress diagnostics without response/credential echo,
caller-owned cancellation and independent best-effort cleanup. There is no native
compute kernel, hard real-time preemption, actuator or hardware qualification
requirement. The previous language choice receives no presumption of correctness.

Current primary-source comparison (2026-10-10):

| Candidate | Decisive property |
| --- | --- |
| TypeScript/native fetch with narrow rejection handling and explicit checkpoints | The [DOM signal contract](https://dom.spec.whatwg.org/#interface-abortsignal) exposes an abort flag and arbitrary JavaScript reason. Checking the flag without throwing that reason lets this public module separate stop behavior from diagnostics. Narrow Promise catches preserve application callback and parser error identity. |
| Kotlin coroutines | [ensureActive](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines/ensure-active.html) supports cooperative checks in code that does not suspend. It provides a credible lifecycle model for a future JVM client, but synchronous work still needs checkpoints, and a diagnostic policy is still necessary. No measured advantage justifies a JVM/JS bridge for this Node-facing module. |
| Dart Futures | [Future error handling](https://dart.dev/libraries/async/futures-error-handling) permits scoped handlers and cleanup; handlers placed after a callback can also capture that callback's error. It does not remove the need to distinguish transport from application failures. A Dart client remains a separate deployment candidate, not an evidenced improvement to this Node boundary. |
| A blanket outer error normalizer | This would erase parser categories and caller-owned renderer errors. Existing renderer-identity controls reject that tradeoff; catches belong only around transport promises. |

**KEEP TypeScript/native fetch; FIX error boundaries and cooperative cancellation.**
Three narrow rejection handlers produce new fixed errors without retaining causes.
Checks after a completed reader operation and after each display callback stop
before the next generator step can parse a buffered event. The existing renderer
failure override and independent DELETE cleanup remain intact. Neither foreign
runtime performance nor universal cancellation latency is claimed.

Sixteen controls cover nine transport error values, five real HTTP/native-fetch
cancellation points, and two same-chunk callback cancellation tails. The initial
14-case run had 13 assertion failures and one pass; adding the two tail cases
produced 15 assertion failures and one pass before production changes. The
corrected source suite includes all 16 cases and prior callback-error controls.
Tests use synthetic local data; no private endpoint or credential is contacted.
Five-second native-test watchdogs only bound regression hangs.

Limitations: synchronous callbacks/parser work cannot be preempted by this check;
custom implementations that ignore abort can retain resources; cancellation before
admission cannot prove remote viewer deletion. Diagnostics intentionally no longer
expose native abort error names; callers inspect their own signal. Application
callback exceptions are intentionally not sanitized. Initial endpoint trust,
lexical-number equivalence and producer payload/whole-event bounds remain in the
open transport review. Distribution/tooling and remaining platform/P12 inventory
have not completed V3 review. No completion marker is created. See the
[source-bound record](evidence/phase3/p33-errors-review-v3.json).


## Third component, endpoint origin admission slice

Baseline `66ff8a2650f3499d2fdaf1a605556989ec8c5031`. The earliest generated
admission and observation controls were rechecked with the full focused client
regression run. Raw base concatenation admitted paths/query/fragment components
and made a trailing slash produce a double-slash API route. It also allowed
plaintext remote URLs despite the documented loopback/TLS deployment boundary
in [edge usage](../../usage-edge.md). Caller-selected endpoint trust was documented,
but the client did not enforce even that transport shape before attaching credentials.

Constraints: accept one explicit server origin for a read-only Node client;
preserve literal loopback development; require HTTPS for other hosts; reject
userinfo and URL components that change API routing; normalize only the optional
terminal slash; expose a fixed diagnostic before any fetch. This is endpoint
admission, not server authorization, TLS qualification or an SSRF sandbox.

Current primary-source comparison (2026-10-10):

| Candidate | Decisive property |
| --- | --- |
| TypeScript + host WHATWG URL | [Node URL documentation](https://nodejs.org/api/url.html#the-whatwg-url-api) exposes origin and parsed scheme/host separately from credentials/path/query/fragment. Using the host parser and comparing input with its origin avoids a second parser disagreeing with the actual fetch runtime. Local Node 22 tests verify the chosen behavior; the current documentation is not a claim that Node 26 was tested. |
| Rust `url` | [Url parsing and origin](https://docs.rs/url/latest/url/struct.Url.html) provide a credible native structured-URL interface. A Rust boundary still needs explicit scheme and origin policy. Moving this small guard across FFI/Wasm adds a second interpretation boundary without a demonstrated throughput or isolation need; a separately deployed native client is not evaluated by these Node tests. |
| C#/.NET `Uri` | [IsLoopback](https://learn.microsoft.com/en-us/dotnet/api/system.uri.isloopback?view=net-9.0) is a semantic helper, not this policy: its documented accepted cases include names and local file URIs. Explicit protocol/authority restrictions remain necessary. A .NET implementation offers no demonstrated security advantage for the existing Node fetch boundary. |
| Handwritten URL regex or raw string concatenation | A regex would need to reproduce host parsing and normalization; concatenation already fails the query/fragment/trailing-slash controls. Neither supplies the required structured interpretation unaided. |

**KEEP TypeScript/host URL; FIX origin admission before credential construction.**
Input must exactly equal the parser's origin, with one optional trailing slash.
This deliberately rejects parser-repaired aliases, casing, default-port spellings,
userinfo, path prefixes, query/fragment markers and non-string coercion. HTTPS is
admitted; HTTP permits only `127.0.0.1` or `[::1]`. The returned origin constructs
all three fixed paths. A caught parse failure is replaced by `invalid_endpoint`,
without the rejected value/cause. No DNS request, new dependency or server policy
implementation is added. This is a documented tightening of the client contract,
not a frozen server schema or threshold change.

Forty-eight controls cover 38 rejected inputs, seven admitted origins and three
native IPv4 HTTP cases. Baseline retains 45 assertion failures and three passing
controls; there are no test execution errors, skips or cancellations. Actual
loopback requests independently expose query/fragment path corruption and the
double-slash route. HTTPS and IPv6 cases check request construction through a
controlled fetch only. Native five-second watchdogs bound regression hangs, not
production latency. Caller-selected origins remain trusted configuration; host
proxy behavior, TLS trust, DNS policy and local privileged networking remain
outside this helper's guarantees.

Endpoint shape is now reviewed; production TLS deployment remains an external
integration gate with no qualification claimed. The next earliest transport
questions are lexical numeric equivalence and the producer payload versus consumer
whole-event limit. Distribution/tooling and the remaining platform/P12 inventory
are still incomplete. No completion marker is created. See the
[source-bound record](evidence/phase3/p33-endpoint-review-v3.json).


## Third component, integer token admission slice

Baseline `39956fd924fcdf1c2d65b16a5b998003892cfcba`. The earliest generated
admission, observation projection and clock controls were rerun before advancing
this transport correction. Native JSON parsing rounds numbers before AJV sees
them: fractional source values can become apparently valid integers. Decimal and
exponent forms also differ from the producer's strict integer model. JSON Schema
itself [treats 1 and 1.0 as the same integer](https://json-schema.org/understanding-json-schema/reference/numeric);
this is an explicit client wire restriction, not an AJV defect or schema rewrite.

Constraints: retain the closed versioned API, 64 KiB whole-event and depth bounds,
safe integer counts/timestamps, fractional geometry, escaped property decoding,
fixed diagnostics and Node package deployment. No native binary installation or
hardware timing guarantee is needed. The producer's `Closed` strict configuration
and `StrictInt` constant guards are read-only contract inputs, not modified here.

Current primary-source comparison (2026-10-10):

| Candidate | Decisive property |
| --- | --- |
| TypeScript with native source-aware JSON reviver | [TC39 source access](https://github.com/tc39/proposal-json-parse-with-source) exposes original primitive tokens after native parsing. The executed Node 22.23.2 controls recover the distinction without a second JSON grammar or runtime boundary. |
| Go `encoding/json` | [UseNumber and Number](https://pkg.go.dev/encoding/json) retain a numeric literal for explicit conversion. This is a credible native client option, but replacing the Node parser with a process/Wasm boundary offers no demonstrated isolation or resource benefit for bounded records; explicit schema and integer policies would still be needed. |
| Rust `serde_json::Number` | [Integer classification](https://docs.rs/serde_json/latest/serde_json/struct.Number.html#method.is_i64) distinguishes integer representation from decimal forms. A native client can use this directly. An FFI/Wasm replacement for this Node-only parser still needs host transport integration and safe-range policy; no measured requirement favors that migration. |
| Extending the handwritten preflight into a number parser | Would duplicate escape, key and token handling already supplied by the host. The existing preflight remains limited to duplicate keys/depth; source-aware native parsing provides the missing token evidence. |

**KEEP TypeScript/native JSON; FIX integer token admission.** Generate immutable
integer-property metadata alongside validators from the closed API bundle. At
parse time require integer spelling and a safe integer value for these fields;
missing source capability rejects the event. The current schema has no integer
array items or names reused for floating-point fields. Its ten integer names are
also pinned independently in tests; future schema changes require review of that
assumption. Full schema validation still follows. The narrower wire profile does
not claim arbitrary decimal precision for geometry; direct `Observation.accept()`
input has already lost numeric spelling.

Thirty-six new controls cover nine integer paths, three disallowed spellings,
health/gap sequence fields, escaped keys, missing runtime support and five positive
cases. The corrected pre-implementation RED run has 28 assertion failures and
eight passes; three genuinely fractional zero values already failed admission.
The initial run also exposed a malformed positive reason-text fixture, which was
corrected before production edits; both reports are retained. Independent generated
metadata admission failed once before implementation. After correction, 226 source
controls and five validator controls pass; installed-package results are recorded
in the evidence artifact. This is bounded behavioral evidence, not a cross-runtime
performance benchmark or full producer/client qualification.

The producer currently caps JSON payload bytes while the consumer caps the whole
SSE event. The existing maximum-payload negative control remains rejected; no
frozen bound is relaxed. Reconciliation remains an open producing-lane contract
question. Distribution/tooling and the remaining platform/P12 inventory have not
completed this review. No completion marker is created. See the
[source-bound record](evidence/phase3/p33-numeric-review-v3.json).


## Fourth component, package manifest and license inputs

Baseline `de3ccb15ff92321b4b5ddb649ba204c7c51a1e44`. Fresh admission,
projection, clock and transport regression checks remain green. Protected main
`a7704008f0f59cbd7b4d56d3cefb5ff28bd9eb46` still caps producer JSON payloads
rather than complete SSE events. The negative boundary control and producing-lane
handoff are retained; no peer module or frozen threshold changes here. Independent
package review found `files: ["dist"]` admitted stale modules, diagnostic records
and nested npm cache logs. The archive omitted the repository license text.

Constraints: distribute only reviewed Node ESM code/declarations/schema and package
metadata; preserve installed behavior; use the package manager's actual manifest;
exercise dirty output directories without deleting unrelated files; run on the
prepared Node CI platforms without an additional runtime or native build.

| Candidate | Decisive property and current evidence |
| --- | --- |
| npm JSON file allowlist + Node regression | [npm files semantics](https://docs.npmjs.com/cli/v11/configuring-npm/package-json#files) permit explicit file selection and automatically include certain metadata. An exact dry-run manifest assertion checks both. [Node execFileSync](https://nodejs.org/api/child_process.html#child_processexecfilesyncfile-args-options) provides shell-free arguments and bounded captured output; the test invokes the same npm JavaScript CLI through Node, avoiding platform command shims. |
| Yarn or pnpm pack | [Yarn pack](https://yarnpkg.com/cli/pack) and [pnpm pack](https://pnpm.io/cli/pack) offer archive tooling. A different manager still needs reviewed file selection; neither supplies an evidenced benefit for this npm consumer contract. No comparative runtime benchmark is claimed. |
| Python subprocess harness | [subprocess](https://docs.python.org/3/library/subprocess.html#subprocess.run) can invoke the same npm CLI. It would add a second interpreter to a standalone Node package's test prerequisites without replacing npm's file-selection semantics. KEEP the regression in Node; this is a deployment requirement, not an incumbent-language preference. |

**KEEP npm package format and Node test host; FIX explicit artifact inputs.**
The manifest names ten build files and the unchanged repository license copy.
Two regression assertions require the exact archive file set and license bytes.
The test creates only a unique synthetic directory, runs offline dry-run packing
with scripts disabled, and removes that directory in `finally`. Its subprocess
has a 20-second timeout and 1 MiB output cap; these are test controls, not a runtime
or hardware latency claim. Existing CI invokes the new test through `npm test`.

Both baseline assertions failed. The packing output included three synthetic files
and two cache entries; the license was absent. The baseline used the system npm
CLI, and the corrected check also executes the prepared Node installation's npm
CLI; tool versions and failures are retained in the evidence. A wrong-directory
edit attempt made no source changes, and an initial corrected run failed from
host thread exhaustion. Neither is counted as a product assertion failure.

The allowlist does not detect altered contents in permitted files or prove a fresh
build. It is not a general secrets scanner, legal compliance assessment, browser
qualification or public SDK release. Full source/build provenance and generated
declaration/schema parity remain the next distribution review items; the overall
P3.3/P12 audit remains incomplete. See the
[source-bound record](evidence/phase3/p33-package-review-v3.json).


## Fourth component, declaration/schema generation and drift admission

Baseline `08dae57139be0d84d3320d327205923f2927151c`. Rechecked earlier
admission, projection, clock, session and transport controls before continuing
through distribution. The Python generator flattened every array into a variable
length TypeScript array, including four contract fields with equal minimum and
maximum widths. The standalone package build also lacked a contract drift gate.

Constraints: generate declarations plus the exact API-v1 runtime schema from the
checked-in OpenAPI document; run source-package build/checks on Node without a
second interpreter; preserve the reviewed runtime transport; reject unsupported
schema evolution; require explicit regeneration instead of repairing drift during
a check. The input is a trusted repository build artifact, not a network document.

| Candidate | Decisive evidence |
| --- | --- |
| Python standard-library generator | Can produce both outputs, but the standalone Node source build would require a second interpreter for drift checking. No Python-specific dependency or semantic requirement exists in this transformation. The historical implementation also replaced reference-like annotation text globally. |
| Node ESM with native JSON and filesystem | [Node filesystem APIs](https://nodejs.org/api/fs.html#fsreadfilesyncpath-options) support deterministic local build inputs. A single Node build tool can check both generated files without another runtime or dependency. Exact baseline parity and focused rejection tests support this bounded choice. |
| TypeScript openapi-typescript | [Official advanced documentation](https://openapi-ts.dev/advanced) covers richer schema typing, including fixed tuples. It is a credible candidate if the vocabulary expands. It supplies declarations rather than this package's runtime schema bundling/check contract, which would still need an adapter. No startup or speed advantage is asserted for the custom tool. |
| Java OpenAPI Generator, TypeScript fetch target | [Official generator documentation](https://openapi-generator.tech/docs/generators/typescript-fetch/) provides a broader client-generation ecosystem. This slice requires models and a runtime schema, while retaining the reviewed transport. Its Java build dependency and broader templates offer no demonstrated advantage for the present closed contract; no parity or performance claim is made for this candidate. |

**MIGRATE generation from Python to Node ESM; FIX tuple widths and build drift
admission.** The old Python command is a compatibility forwarder to the sole Node
implementation. `--check` is read-only; `--write` is explicit. Schema references
are rewritten only in schema locations, preserving annotation text. Unsupported
keywords, unknown primitive types, external/dangling references and open objects
are rejected. Fixed tuple expansion is limited to 32 entries as a build-tool
constraint, not a change to frozen runtime limits. This is a deliberately narrow
API-v1 generator, not a complete OpenAPI implementation.

[TypeScript tuple semantics](https://www.typescriptlang.org/docs/handbook/2/objects.html#tuple-types)
match the fixed centre, box, covariance and velocity widths. Positive and negative
compilation fixtures check all four. The corrected baseline fixture fails with
four unused expected-error directives; the migrated declarations pass. An initial
positive covariance fixture incorrectly used four entries instead of the published
two and was corrected before the final baseline run. The first generator test
also caught inherited object-property lookup for an unknown primitive; a Map now
performs that lookup. Both negative reports are retained.

The runtime schema remains byte-identical to baseline. Declaration parity differs
only in the four widths and generator attribution. Source, installed artifact,
strict type and compatibility checks are recorded in the
[source-bound evidence](evidence/phase3/p33-generation-review-v3.json). These are
Linux/Node software checks, not browser/native qualification or hard real-time
measurements. A local contract drift check does not authenticate the producing
OpenAPI export or establish reproducible release provenance. Those distribution
boundaries and the remaining platform/P12 inventory still need fresh review;
no lane completion marker is created.


## Fourth component, installed-client smoke result validity

Baseline `57d5dbe0848e9febad54025b75d813077890b275`. Fresh SDK admission,
projection, clock and transport regression checks remain green. The producer's
`test_openapi.py` already compares its live model export with the checked-in
OpenAPI artifact; its dependencies are absent from this host's system Python, so
this turn does not claim a new executed producer-export check. No producer files
were changed. Review of the consumer smoke harness found a stale `AbortError`
expectation after the client switched to fixed transport errors. It also reported
display callbacks as wire events, wrote UNKNOWN without checking callback state,
and could leave an old success report after a failed run.

Constraints: execute the actual Node program, consume the producing lane's
Python `HTTPService` lifecycle fixture without duplicating its configuration,
install only the prepared archive offline, distinguish expected caller shutdown
from all other errors, and prevent stale results from appearing current.

| Candidate | Decisive property |
| --- | --- |
| Python orchestration plus Node consumer | [Python subprocess](https://docs.python.org/3/library/subprocess.html#subprocess.run) executes argument lists with failure propagation and a child timeout; direct access to the existing Python service fixture keeps one service-bootstrap definition. [Node package resolution](https://nodejs.org/api/packages.html#module-resolution-and-loading) exercises the package import in the external consumer directory. |
| Node-only orchestration | Can host the client but still requires a Python fixture bridge or a second implementation of server setup/cleanup. It does not eliminate the Python server/test dependency at this integration boundary. This differs from the standalone generator, where migration removed that dependency. |
| PowerShell process orchestration | [Start-Process](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/start-process?view=powershell-7.5) provides process launch, waiting and stream redirection. It still needs both Python and Node, and a bridge to the service fixture; no demonstrated correctness or deployment benefit justifies a third runtime here. No comparative performance claim is made. |

**KEEP Python/Node integration boundary; FIX result validity.** The harness checks
every displayed current state, accepts only its own cancellation paired with
`stream_unavailable`, and reports `display_callbacks`. Watchdog renders can repeat
an observation; this count is not distinct wire evidence. The previous report is
removed before import/install/server prerequisites, and only successful execution
writes a new report. Historical reports are retained unchanged.

Eight regression methods failed against baseline, with no test execution errors.
They now pass, covering expected cancellation, other errors before/after abort,
legacy abort rejection, missing observations, false state, reporting semantics
and stale result removal. A ninth control executes the built SDK with controlled
fetch/clock responses and requires DELETE cleanup. Its initial JavaScript fixture
escaping error is retained separately from baseline product failures. The final
nine methods and 235 SDK controls pass. Tests exercise the actual child program;
package installation and the Python service boundary are substituted in these
harness controls. They do not qualify a fresh real-server installed run, Windows,
macOS or a customer distribution. See the
[source-bound evidence](evidence/phase3/p33-smoke-review-v3.json).

The archive's fixed filename does not bind it to the current source revision.
Archive/source binding and actual real-server execution remain the next distribution
review items. P19 and its complete offline bilingual contextual Help Center
requirements were read; no P12/P19 UI or acceptance claim is made before this
lane's outstanding re-audit and applicable integration gates are complete.


## Fourth component, fresh archive and smoke input binding

Baseline `f066e2536c6d3a09b63a150b8d5e1cdea626c3e0`. The fixed archive path
could select a package built from older sources. A successful report could also
be written before server teardown failed. This slice corrects the harness boundary;
it does not establish a signed release or production-service qualification.

Constraints: use the actual npm pack/install behavior, build from the current
SDK checkout, retain the producing lane's service fixture, perform no deployment
time dependency fetch, isolate each archive, and reject changed inputs/results.
The Python/Node versus Node-only/PowerShell reassessment above still applies:
Python owns the existing service lifecycle, while npm owns package construction
and Node owns client execution. No additional runtime eliminates either required
boundary. [npm pack](https://docs.npmjs.com/cli/v11/commands/npm-pack/) provides
JSON metadata, an explicit destination and ignored lifecycle scripts;
[Python hashlib](https://docs.python.org/3/library/hashlib.html) provides incremental
SHA-256 without a new dependency. **KEEP these boundaries; FIX archive selection
and source/result consistency.** The actual build/pack/install probe below is
executable evidence, not a comparative latency or cryptographic certification claim.

Each smoke run explicitly builds the SDK, packs offline into its unique consumer
directory and installs that archive with lifecycle scripts disabled. Pack metadata
must identify one local `.tgz` basename. Build, pack and install child timeouts
are 60/30/30 seconds; the existing client timeout remains 20 seconds. These are
harness limits, not product deadlines. Root SDK source/configuration/docs matching
`.mjs/.ts/.json/.md`, its license, every `src` file and the OpenAPI input are hashed.
The archive digest and input map are checked after packing, after installation,
and after server cleanup. Only then is success published with both bindings.
The temporary archive is removed by the existing temporary-directory lifecycle.

The corrected baseline retained five assertion failures and eight passing methods,
with no execution errors. Fifteen final methods pass, including stale archive
avoidance, changed source/archive rejection, invalid pack metadata, cleanup failure,
and source change during cleanup. Six metadata cases exercise the same method.
Earlier SDK regression controls are rechecked independently. See the
[source-bound evidence](evidence/phase3/p33-archive-review-v3.json).

`python3 tests/integration/node_consumer_loopback.py` additionally exercises actual
build, pack, offline install and the installed client over IPv4 loopback, using a
small explicit synthetic HTTP fixture. It requires prepared Node dependencies and
the same offline npm cache as the real smoke. It checks POST/GET/DELETE, labels its
report as a substituted service, clears its previous report, and removes the generic
smoke result so it cannot be mistaken for production-service evidence. It does not
import the production Python service or qualify hardware. Its final report records
three display callbacks, UNKNOWN, archive digest and current input hashes.

Hashes identify local bytes; they do not authenticate a compiler, installed npm
runtime dependencies, a source revision or a remote publisher. Persistent changes
between checkpoints are detected, but transient change-and-restore races or a
hostile local process are outside this harness. A fresh actual production-service
run and remaining distribution/platform/P12 review are still outstanding. No audit
completion marker or P19 acceptance status is issued.

## Fourth component, production-service execution and CI reachability

Baseline `33ada4ce0571124474f49c4cb9dc56badb0d123e`. Fresh reads of client
admission, projection, session parsing and wire framing preserve the previous
versioned bounds and UNKNOWN display behavior. The archive bridge commit's six
paths and 44 source hashes match the reviewed bytes. The next distribution audit
found no workflow job invoking `scripts/edge_node_e2e.py`: unit tests and the
controlled loopback probe could not establish that this real-service consumer
path executes in CI. The parsed baseline reachability check failed as expected.

Constraints are a bounded, unprivileged hosted Linux job; locked dependency
preparation; offline npm installation during the actual smoke; and retained
failure logs. The peer service remains a source-checkout subprocess through its
published test fixture, and the Node client is installed from a fresh archive.
**KEEP the Python/npm/Node boundary; FIX CI reachability.** GitHub's
[workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
requires YAML. Bash directly composes the existing commands and fails pipelines
on errors. PowerShell or a Node orchestration wrapper would still launch Python
and npm and would add another command/error mapping for this Linux-only check;
no runtime or interoperability benefit is established. This correction selects
no new product runtime and makes no cross-language performance claim.
[npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci/) prepares the locked cache;
the existing smoke then packs and installs offline. Dependency preparation still
needs package registries; this is not an air-gapped distribution qualification.

The new client-owned workflow uses pull-request/main/manual events, read-only
permissions, commit-pinned actions and checkout without persisted credentials.
Its path filters cover the SDK, OpenAPI/fixtures, producer/core code, replay,
service/smoke tests and smoke entry point. A ten-minute job runs focused client
checks and the actual-service smoke. Shell logs, the checked-out revision and
success JSON (when available) use
[artifact retention](https://docs.github.com/en/actions/tutorials/store-and-share-data)
even after step failure. No peer-owned workflow or service implementation changed.
Static reachability, 20 representative trigger cases, shell syntax and actionlint
pass; these checks do not substitute for a hosted workflow run.

The system Python lacked service dependencies. Installing the exact hash-locked
binary dependencies into an isolated lane-local environment enabled the actual
service run without a VM, image/model download or vision extras. It passed with
three delayed display callbacks, UNKNOWN state and the expected current archive
and input hashes. This service uses synthetic replay; the service itself is not
an installed release artifact. The earlier substituted-service results remain
historical evidence with their original limitations. The optimization-mode probe
also passed all 15 existing harness methods and did not reproduce a defect.
See the [source-bound results](evidence/phase3/p33-service-ci-review-v3.json).

Remaining: hosted execution of the new workflow, broader distribution/platform
review, producer/consumer SSE-size reconciliation and the unimplemented P12
operator client. P19/UI/help, device qualification, signed customer distribution
and lane completion remain unclaimed.

## Fourth component, installed public observation declarations

Baseline `e7404949e324950834157d892b4cabdbeb44c1ab`. Restarted review of
admission, projection, transport and distribution found that inferred declaration
output widened the guaranteed `current_state: 'UNKNOWN'` and both display labels
to `string`. An external consumer could not narrow expired versus delayed views.
The new test packs the actual archive, installs it offline outside the checkout
and compiles only against its public package entry point. Before correction it
failed with seven TS2322 assignment diagnostics; package resolution succeeded.

Constraints: preserve the existing JavaScript host APIs and runtime behavior,
provide accurate TypeScript declarations to npm consumers, preserve the API-v1
observed-state/source vocabulary, and avoid a new runtime dependency. **KEEP
TypeScript; FIX the exported view boundary with an explicit discriminated union.**
The [TypeScript narrowing rules](https://www.typescriptlang.org/docs/handbook/2/narrowing.html#discriminated-unions)
support branch-specific fields through literal labels; the
[declaration-file model](https://www.typescriptlang.org/docs/handbook/declaration-files/introduction.html)
lets consumers check this without executing the fixture. Kotlin/JS is a credible
alternative with [JavaScript and TypeScript exports](https://kotlinlang.org/docs/js-to-kotlin-interop.html),
but would still require an explicit export boundary and host interop for this
fetch/stream client. ReScript/genType, Dart/JS and Rust/Wasm were considered in the
broader SDK reassessment; this declaration-only defect establishes no new native
compute or shared JVM requirement that materially favors those alternatives.
No cross-language performance win is asserted. A handwritten declaration would
duplicate the implementation signature; `as const` would introduce readonly
array semantics beyond this correction. The explicit return annotation checks
both implementation branches and generates the public union from the same source.

The built `client.js` SHA-256 is identical before and after the correction.
The 235 focused runtime controls pass with string code generation disabled,
as do the three package tests and existing tuple assignment compilation. The
first post-fix package run timed out in the compiler while other checks were
running; the failure is retained. An isolated retry passed with the same 30-second
child timeout. No frozen bound was relaxed. Type declarations are not runtime
validation, authorization or an immutability guarantee; callers still receive
mutable copies. See the [source-bound results](evidence/phase3/p33-public-types-review-v3.json).

The inventory still lacks Android/JVM modules, desktop launch/install lifecycle
and the P12 operator application. The existing camera demonstration is not P12
completion. Review and implementation of those owned boundaries, the producer
SSE-size mismatch and the P19 UI/help contribution remain outstanding. This slice
does not issue an audit completion marker or customer/physical qualification.

## Fourth component, offline installed lifecycle coverage

Baseline `2c316fb17fca17aacd4fa09fff635c8df7a422d8`. The previous package
tests exercised install, types and a service smoke but did not verify uninstall
or reinstall. This is a coverage gap; no production defect or production RED
is claimed. The initial review-status table also still described transport and
generator corrections as pending even though later sections recorded them. The
table is corrected; historical baseline sections remain evidence of their time.

Constraints: use the package consumers actually install, exercise npm manifest,
lockfile and module resolution semantics in an external directory, avoid registry
requests and lifecycle scripts, and check runtime behavior in fresh Node processes.
**KEEP Node/npm for this distribution check; FIX executable lifecycle coverage.**
[npm uninstall](https://docs.npmjs.com/cli/v11/commands/npm-uninstall/) owns the
installed-package and dependency-record removal behavior. A Python or PowerShell
runner can invoke it, but still needs Node to test the public ESM import boundary;
neither provides a different installation or isolation guarantee. Another package
manager would test a different consumer contract. The choice follows the actual
artifact boundary, without a speed or universal language-superiority claim.
[Node exports](https://nodejs.org/api/packages.html#package-entry-points) controls
package subpath imports; it is not an operating-system access control boundary.

The external runtime fixture uses the existing synthetic blackout result and
checks default UNKNOWN, admission at the inclusive lease boundary, detached
copies, expiry, invalid-input withdrawal, disconnect and blocked internal subpath
imports. It runs with string compilation disabled before removal and after
same-archive offline reinstall. Removal checks the package directory, dependency
manifest, lock entry and module resolution in a fresh process. The temporary
consumer is removed in `finally`; each child retains a 30-second timeout and
1 MiB output cap. The fixture requires a nonempty observation and prints success
only after all assertions. No runtime source or frozen threshold changes.

This does not establish cross-version upgrade, global uninstall, removal of an
already-imported module from another process, cache erasure, a desktop installer,
Android support or P12/P19 acceptance. The safe embedded engineering addendum was
read; its informational UNKNOWN and documented-interface requirements apply to
these client boundaries, with no weapon-specific integration. The next owned
work remains platform lifecycle and P12 readiness. No audit completion marker.

## Current SDK checkpoint and first P12 presentation component

Baseline `f133a6fae9dd3cdaa2707d0351c6c9233bdb005c`. Re-read the current
admission generator, projection/clock, session/wire, service-smoke and package
lifecycle boundaries against the earlier component-specific decisions. The
five-file lifecycle bridge commit and its 49 source bindings match. Keep the
generated schema validation, TypeScript/host transport, private projection,
Node contract generator and Python/Node service fixture boundaries for the
reasons above; no new migration winner or production correction was demonstrated
in this pass. The history walk covers the original client through the latest
installed-package slice. Cross-version upgrades and platform implementations are
remaining delivery work, not evidence of already implemented support. The
producer SSE size disagreement remains a producing-lane contract handoff.

The first P12 component is now a reusable observation presenter in
`examples/operator`, with its own strict ADR schema and four C4 views in
[`P12-001`](../../../examples/operator/adr.json). It consumes an aggregate SDK
view and supplies fixed English/Swedish title, explanation and help-topic ID;
no DOM or application shell is implemented yet. Current state always remains
UNKNOWN. Invalid projections withdraw source details; input exceptions cannot
become display text. No track/session IDs, raw geometry or covariance are returned.
This is a presentation check, not source authorization or a new freshness lease.

Constraints are a small synchronous mapping, explicit state/locale types, no
runtime dependency and no raw sensor or persistence boundary. TypeScript/native
ECMAScript directly describes that contract. Plain ECMAScript would need separate
type checking/declarations; Elm ports or ReScript foreign-function bindings add
no demonstrated guard to this mapping; Lit's DOM lifecycle belongs to a later
rendering component. **KEEP the SDK interoperability boundary; SELECT TypeScript
for this presenter.** No framework or bundler is selected yet. The ADR records
primary-source alternatives and the absence of performance/qualification claims.

Tests first failed because the new module was absent. The initial implementation
then exposed three sparse-array guard failures: ordinary `some()` skipped holes.
Dense iteration fixes all three. Final tests cover both locales, authority and
unknown-field rejection, source copying, nonfinite/malformed arrays, throwing
getters and actual SDK admission/expiry composition. ADR validation rejects
unexpected claim fields. The client-owned CI initially lacked operator path
triggers and execution; three static checks now pass and actionlint is clean.
Hosted execution is still pending. See the
[source-bound evidence](evidence/phase3/p12-presenter-v1.json).

The presenter requires a fresh `Observation.view()` at render time; holding an old
projection does not establish freshness. Direct object cloning precedes shape
validation and has no pre-clone byte bound. This is not the P12 application or
P19 Help Center: accessible DOM interaction, navigation, provenance/permissions,
release-SHA-bound bidirectional help coverage, browser testing and independent
customer acceptance remain executable work. No lane/audit completion is claimed.

## P12 native observation panel and disposal review

Baseline `2f22c34c716852d5b562d99bb5fb4eb20f59fa2a`. The presenter bridge
commit, eleven paths and all 57 recorded source hashes were verified before
publishing to PR #44. Re-read the earlier SDK projection/clock, wire/session,
contract/validator generators, package lifecycle and real-service fixture source,
then the new presenter. KEEP these bounded component decisions: generated runtime
schema guards, private aggregate projection, host Fetch/Streams transport, Node
contract generation, and Python's reuse of the peer service test harness. Existing
negative timing/provenance and full-event-versus-payload size evidence remains;
there is no new physical qualification or migration winner in that pass.

The next reusable P12 slice is `mountObservationPanel`: stable native language
buttons, UNKNOWN status and contextual Help/Hjälp disclosures backed by the actual
presenter. The host supplies a fresh SDK view reader and owns scheduling, transport
and authorization. Language/help activation re-reads that view. Reader failures
withdraw details; disposal clears owned text/content and removes event listeners.
Late callbacks cannot repopulate the panel, including disposal during an input
getter. Repeated identical refreshes retain text nodes while still reading a new
view. The panel itself performs no network request, persistence or timer operation.

SELECT TypeScript/native DOM for this fixed component after comparing ordinary
ECMAScript, Lit, Elm and ReScript against explicit lifecycle, offline text, static
DOM typing and host integration requirements. No benchmark or general framework
superiority is claimed. [P12-002](../../../examples/operator/panel-adr.json) records
the decision, primary sources and four C4 views under a closed schema. Lit's
reactive web components and Elm's port/message boundary remain credible larger
application options; neither removes the current input/host trust boundary.
LinkeDOM is lock-pinned for development-only structural tests, not a browser.

Verification retained eight missing-renderer assertion failures, followed by eight
passes. Two new disposal regressions then exposed retained text nodes and getter
repopulation; both were corrected. The initial repeated-text identity assertion
exhausted the test runner's configured heap while formatting a DOM-object diff.
That failure remains recorded. A bounded boolean assertion and an isolated copy
with the original unconditional assignment demonstrate the intended assertion
failure without exhaustion; the guarded implementation passes. Final focused
results and source bindings are in
[evidence](evidence/phase3/p12-panel-v1.json). Offline lock installation, dependency
audit and workflow lint were checked. CI now prepares this component's locked
structural test dependencies before running its tests.

Two bounded local Chromium probes timed out (read-only profile access, then host
DBus/NSS diagnostics). Security settings were not disabled. DOM tests do not prove
keyboard/focus behavior, screen-reader announcements, rendered contrast or browser
interoperability. Host stalls may retain explicitly delayed historical text until
refresh; current conditions remain UNKNOWN. No role-sensitive instructions are
shipped. Authentication, release-bound help inventory/search, onboarding, full
scene/map/replay application, installed customer walkthrough and P19 integration
remain unfinished. The safe embedded addendum's informational UNKNOWN/interface
requirements apply; no weapon-specific sample was imported. No audit/lane
completion marker is warranted. Next: execute the panel in a supported browser
harness and integrate its host refresh/lifecycle adapter.

## P3.3 admission and P12 refresh re-entry correction

Baseline `1e99e94a50b725169ef9a3b41720100ad3563c28`. Verified the preceding
panel bridge commit, thirteen paths and 64 source hashes. Restarted at SDK
admission, then reviewed the existing projection, transport, generated contracts,
package lifecycle and P12 presenter/panel boundary. A valid direct input getter
could disconnect, read the cleared state or admit another observation during
cloning, yet the interrupted outer admission restored its own observation. Three
new SDK assertions reproduced this. Admission now uses a private opaque token;
revocation during cloning rejects with `invalid_event` and clears all state,
including any nested admission. A later independent acceptance remains supported.

The panel had the corresponding ordering defect: a nested reader/getter refresh
could withdraw details, then an older refresh restored them. A nested locale
change could mix English guidance with Swedish labels. Three panel assertions
reproduced these cases. Only the latest refresh token may now publish to the DOM;
disposal invalidates it. This adds no queue, retained observation history, timer
or network operation. It does not bound arbitrary host callback recursion or make
in-process JavaScript an isolation boundary. JSON wire input cannot carry getters.

The deployment constraints remain browser/Node JavaScript hosts, fixed aggregate
contracts, explicit revocation, no persistent personal identifiers and no
qualified real-time deadline. KEEP TypeScript with generated runtime validation
for SDK admission and native DOM for this panel. Reconsidered plain ECMAScript,
ReScript, Elm ports, Lit reactive components and the prior native/Wasm boundary
options: a static type system alone cannot validate incoming JavaScript, and a
different UI scheduler still needs explicit ordering at this callback boundary.
The [structured serialization algorithm](https://html.spec.whatwg.org/multipage/structured-data.html#structuredserializeinternal)
reads property values; [Lit updates](https://lit.dev/docs/components/lifecycle/#reactive-update-cycle)
and [Elm ports](https://guide.elm-lang.org/interop/ports.html) describe different
integration models. The KEEP conclusion is an engineering inference from those
interfaces and these executable regressions, not a measured language performance
ranking. No material migration winner was established for these corrections.

The comparison script now explicitly limits parity to its 45 plain-data traces
and 162 views; historical legacy/closure prototypes do not implement this new
revocation rule. The packed consumer also exercises all three interruptions on
both initial installation and reinstall. Final results and source bindings are
recorded in [the correction evidence](evidence/phase3/p33-reentrant-admission-v3.json).
The first concurrent SDK run passed 242/243: the POST-301 test's server received
no request before its two-second abort. All 243 pass with file concurrency one
and the original timeout unchanged. Resource contention is a plausible cause,
not a proven diagnosis; the original failure log remains retained.

Public PR #44 remains at `2f22c34c716852d5b562d99bb5fb4eb20f59fa2a`;
its single snapshot was queued/behind. The panel commit is held locally until
this correction is committed and verified. Existing browser-probe failures,
full-SSE-event versus producer-payload size mismatch, host scheduling limits and
unqualified hardware/security/availability claims remain explicit. No complete
Help Center, integrated application, P19 acceptance or audit-completion claim is
made. Next earliest unfinished component: supported-browser execution and the
P12 host refresh/lifecycle adapter, after delivering this correction.

## P12 display host lifecycle and guidance review

Baseline `c6db2d6a992e8a7610f0f4221bf3e7face8fa6b0`. Verified the bridge's
eleven files, 64 source bindings and eight retained reports, then published the
panel and its correction to PR #44. Restarted at SDK admission/private projection,
then wire/session admission, contract/validator generation, offline package
lifecycle, Python/Node real-service harness and presenter/panel source. The
re-entry guards match the preceding regressions. No new SDK defect or migration
winner was demonstrated. KEEP the static JavaScript-host API with explicit runtime
schema guards, native Fetch/Streams, Node generation and Python's actual service
fixture ownership. The open-universe alternatives and constraint comparisons in
the component sections above remain applicable to this reviewed source; no new
performance benchmark or target-platform qualification was performed.

Fetched `origin/main` at `fce89d3904ddbfb004b55718fab955c91a9c49a0`;
the newly merged sensor documentation does not change the consumed client API.
No peer source or shared policy was edited. The single pre-push PR snapshot at
`2f22c34` was queued/behind. Publication advanced it to `c6db2d6` without waiting
or polling. `gh pr edit` failed on its classic-projects GraphQL query; the same
sanitized title/body update succeeded through the pull-request REST endpoint.

The next demonstrated software gap was the absence of a display lifecycle owner.
SELECT TypeScript/native page events for `mountObservationHost`. The fixed source
interface has only fresh `view()` and `disconnect()`. The adapter clears on mount,
suspension, reactivation and disposal, keeps a single requested 20 ms timer only
while visible, suppresses inactive reads and removes its five listeners on
disposal. Source-clear or scheduler failures latch invalid guidance until remount;
reader errors withdraw details and can recover independently. It never starts or
stops a transport session, authenticates a source, or upgrades delayed data to
current evidence. Callers must own ingress cancellation and source authorization.

The deployment constraint is an offline browser-hosted aggregate display with
explicit lifecycle and no queued history. Compared plain ECMAScript, Lit reactive
controllers, Elm ports and ReScript bindings. Native typed DOM access meets this
small boundary without a runtime framework; Lit component connection hooks do
not replace page visibility/suspension handling, while Elm/ReScript still need
native-event integration. These are scoped interface comparisons, not runtime
performance rankings. Official [page lifecycle guidance](https://developer.chrome.com/docs/web-platform/page-lifecycle-api)
describes task suspension and omitted discard events, so timers are requested
refreshes, never a real-time or reliable suspend-detection claim. The closed
[P12-003 ADR](../../../examples/operator/lifecycle-adr.json) records alternatives,
primary sources, constraints and four C4 views.

Eleven missing-adapter assertions failed before implementation. Further tests
cover reset re-entry, source-read suspension, repeated activation and closed ADR
claims. Two additional failing guidance assertions exposed an integration mismatch:
the existing unavailable help blamed unsupported data even for source/scheduler
failure. English and Swedish guidance now describes unavailable display and
client/service status without inventing a wire-format diagnosis. Topic IDs and
view contracts remain unchanged. See [source-bound results](evidence/phase3/p12-lifecycle-v1.json).

These tests use controlled clocks/events with the actual SDK and a structural DOM.
The Node-tested SDK archive still needs a compatible browser build for complete
browser ingress; the host and panel themselves compile to ESM. Existing browser
probe failures, inaccessible browser/assistive-technology acceptance and the
producer-payload/full-event size discrepancy remain recorded. No full operator
application, release-bound role-aware Help Center, P19 or lane completion is
claimed. Next earliest unfinished component: browser-compatible SDK composition
and a supported-browser lifecycle/keyboard harness.
