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
| P12 reusable operator client | Presenter, panel, lifecycle, connection, browser distribution and bilingual state/action help implemented and reviewed in later slices below; complete scene/map/mission/replay application and product acceptance remain open |
| Android/JVM and desktop product lifecycle | No owned native implementation identified; requirements-driven platform selection and remaining software work are not complete; P11 system install/provision remains peer-owned |

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

## P3.3/P12 browser component packaging checkpoint

Baseline `5a92da58706bbf8b5fd2d398d782f11c2c1c4fba`. Re-read the authoritative
policy and review order, then restarted at SDK admission/projection, wire/session,
generators, package/service harness, presenter, panel and lifecycle. The lifecycle
bridge's ten paths, 68 source bindings and eight reports matched; published that
commit to PR #44. No new defect was demonstrated in those admission boundaries.
The earlier queued/behind CI snapshot was at `c6db2d6`; no CI polling or merge.

KEEP the typed JavaScript-host contracts and generated runtime admission. The
requirements remain native Fetch/Streams/DOM integration, bounded wire admission,
no runtime schema compiler, immediate withdrawal and no stored personal history.
Fresh official [Kotlin/JS](https://kotlinlang.org/docs/js-overview.html) documentation
confirms browser/Node module and multiplatform options. This lane has no existing
JVM consumer requiring shared implementation, so that capability does not establish
a migration win. [ReScript](https://rescript-lang.org/docs/manual/latest/bind-to-js-function)
currently resolves to its language overview, which describes typed JavaScript and
interop; it does not independently verify detailed bindings from earlier research.
[TypeScript](https://www.typescriptlang.org/docs/handbook/typescript-from-scratch.html)
provides static checking while runtime admission must remain explicit. Neither
alternative supplies the missing browser artifact or browser scheduling guarantees
by changing the source language. No cross-language performance ranking is claimed.
Node generator/npm packaging and the Python actual-service fixture remain separate
build/test boundaries; no new competing server or SDK was added.

The next concrete mismatch was packaging: the SDK imported CommonJS generated
validators and a package helper, while native browser ESM cannot resolve that
Node package boundary. SELECT esbuild 0.28.2, pinned as a development dependency,
to bundle fresh SDK/UI compilation into one ESM file. Compared Go/esbuild,
JavaScript/Rollup with official CommonJS support, Rust/Rolldown and direct AJV ESM.
The decisive property is built-in conversion/resolution plus inspectable dependency
metadata without plugins or a second validator implementation, not compiler speed.
See the closed [P12-004 ADR](../../../examples/operator/browser-adr.json) for source
links and C4 views. The Rolldown documentation host failed; its official repository
was available. Only the selected tool was executed.

The output includes nine explicitly allowed runtime inputs, zero external imports,
license bytes and an unsigned compiled-input/output hash manifest. Previous named
outputs are invalidated before compilation; the manifest is written last. Failure
to locate a compiler command removes stale output, and recovery reproduces every
artifact byte locally. The artifact is 133,120 bytes without minification. This is
an observed artifact size, not a memory/latency or browser compatibility bound.
The CI client job now builds/tests and retains it using one Go scheduler thread.

Six initial missing-artifact assertions failed. An additional test run was started
before the first build finished and produced six missing-artifact failures; that
orchestration failure is retained, not represented as a production defect. After
the completed build, six initial checks passed. Expanded checks exercise bundled
authenticated ingress, strict numeric tokens, duplicate keys, fixed error text,
withdrawal, re-entry, bilingual structural rendering, licenses and failed-build
recovery. See [source-bound results](evidence/phase3/p12-browser-component-v1.json).

This resolves packaging only. The public `observe` callback does not expose its
mutable observation as a lifecycle-owned source; a complete browser application
still needs an explicit revocable transport/display integration, not a cached
callback view treated as fresh evidence. Actual browser lifecycle, keyboard,
accessibility and offline installed-product acceptance remain unverified. Existing
Chromium timeouts and the producer-payload/whole-event cap discrepancy remain
negative evidence. P19 role-aware release-bound help, native Android justification
and other unfinished owned UI work remain open; no lane/audit completion marker.
Next earliest unfinished component: supported-browser transport/display integration
and its offline lifecycle/keyboard acceptance harness.

## P3.3 observer setup cleanup correction

Baseline `605db933f2a6b9a0892e4d6fb1e0cd9f6d4b6830`. Re-read the full policy
and review order, restarted at admission/projection, and verified the preceding
browser bridge: 13 paths, 74 source hashes and nine retained reports matched.
Published that verified component to PR #44; the single earlier CI snapshot at
`5a92da5` was queued/behind. No checks were bypassed or polled.

The fresh SDK review found that controller creation, signal composition and timer
startup occurred after session admission but before the try/finally covering
withdrawal and DELETE. A synchronous host setup failure therefore skipped both
cleanup actions and exposed the host exception. Four failing regressions establish
this for signal composition and timer startup, including a final display callback
that itself throws. This is a software lifetime defect; no hardware failure rate
or browser incompatibility was inferred from controlled fault injection.

KEEP TypeScript/native host APIs; FIX the cleanup scope. Optional controller/timer
state now represents partial setup. All three setup operations execute within the
validated handle's cleanup scope; setup failure becomes `stream_unavailable`.
Only allocated timers are cleared, the local controller is aborted if available,
an expired view is delivered and authenticated deletion is attempted. A final
application display exception retains its identity while DELETE still runs.
Successful ingress, callback cancellation and frozen timing/byte bounds are
unchanged. Six setup cases cover all three setup stages with and without display
failure; two more exercise the self-contained browser bundle without string code
generation. Remote cleanup remains best effort, dependent on functioning host
fetch/timeout/cancellation APIs and process survival.

The deployment constraint is asynchronous native-host orchestration with one
admitted session, no queued history and explicit partial resource ownership.
Fresh research compared native TypeScript, plain ECMAScript, Kotlin/JS and
Rust/WebAssembly host bindings. Kotlin's module/platform sharing does not
establish a win for a boundary without a JVM consumer. The official wasm-bindgen
Fetch example still crosses host promises through JsFuture; changing language
would not independently repair server-handle cleanup. The TypeScript choice
keeps static partial-resource checks and direct host interoperation with no new
runtime abstraction. No cross-language speed ranking was performed. The closed
[setup ADR](../../../examples/clients/typescript/observer-setup-adr.json) contains
primary source links, constraints, alternatives and four C4 views. The old
wasm-bindgen documentation explicitly redirected maintenance to its new domain;
the maintained source was read. RxJS's documentation yielded no substantive API
text and the attempted source path failed; no RxJS-specific decision relies on it.

Continued source inspection through wire/session admission, Node contract and
validator generation, package allowlisting/install lifecycle, the Python actual
service harness and P12 presenter/panel/lifecycle/bundler. No additional defect
was demonstrated in those inspected paths. Their established component decisions
remain scoped to the reviewed contracts; this correction is not a full phase or
product completion claim. The earlier browser artifact size/hash evidence remains
historical: this source correction produces a newly hashed bundle.

[Current evidence](evidence/phase3/p33-observer-setup-v1.json) retains RED,
transport/disposal regressions, closed ADR validation, browser parity/reproduction
and package checks. Native browser lifecycle/keyboard acceptance, revocable
transport-to-display integration, release-bound role-aware help and the existing
producer-payload/whole-event discrepancy remain open. Next earliest unfinished
component: a fresh revocable source integration for the browser lifecycle host.

## P3.3 observer timer revocation correction

Baseline `8ade520d4b357775950cc12dff0ba6fd3b875b35`. Restarted from the
admission and observer source after reading the current policy and review order.
Verified the preceding bridge commit against all eight changed paths, 76 source
hashes, seven retained reports and the browser artifact's input/output hashes.
Published that commit to PR #44. The single CI snapshot observed the preceding
`605db933f2a6b9a0892e4d6fb1e0cd9f6d4b6830` head queued/behind; no polling or
check bypass. Prior evidence remains tied to its historical source bytes.

The timer-to-display boundary had a separate mismatch: stream reception checked
cancellation, but the timer could publish an earlier observation after abort
before the reader's promise reaction executed. It also had no terminal guard if
a host retained and invoked its callback after cleanup. Four failing assertions
cover cancellation during a pending read, reentrant cancellation in display, and
retained callback invocation after EOF or invalid-event termination. The latter
is application lifetime fault injection, not evidence that a native browser
normally runs a cleared timer.

KEEP TypeScript/native host APIs; FIX the timer's revocation gates. Each active
timer invocation inspects the combined abort state and disconnects the observation
before reading it if cancelled. The outer finally disables rendering before timer
clear, final withdrawal and independent DELETE. A retained timer cannot invoke
the display after that point, including while deletion is pending. Frozen lease,
event size and timer request values, public API/types and callback error behavior
are unchanged. A native Node HTTP case additionally aborts a real stalled Fetch
response and invokes the timer before the read rejection resumes the observer.
It confirms withdrawal through the native transport without claiming a timing
bound or browser qualification.

Fresh source research compared typed native host orchestration, checked plain
ECMAScript, RxJS Subscription, Kotlin/JS and Rust/Wasm. This is a single-session
callback lifetime, not a reactive ownership graph or a native compute kernel.
The tagged RxJS implementation sets `closed` before finalizers, but that does not
supply this application's signal-to-display check. Kotlin/JS sharing and Wasm
host bindings offer no demonstrated improvement for this component's actual
interoperability requirements. No cross-language speed ranking or installed-tool
preference is claimed. The [closed revocation ADR](../../../examples/clients/typescript/observer-revocation-adr.json)
records current primary sources, constraints, tradeoffs and four architecture
views; its schema rejects extra claims.

The [retained evidence](evidence/phase3/p33-observer-revocation-v1.json) records
four initial failures, six new cancellation/lifetime cases, native loopback,
bundled execution without string code generation, artifact reproduction and
packed-consumer verification. Existing Chromium probe failures and producer JSON
payload versus whole-event cap disagreement remain unresolved. This review and
correction do not complete the full lane audit or P19. No completion marker is
created. Next earliest unreviewed integration: exposing a fresh revocable SDK
source to the P12 lifecycle host without treating callback snapshots as fresh
observations; then complete the remaining component and product-help reviews.

Verification outcome: 64 final transport/error/disposal checks (including two
closed ADR checks), 49 operator checks and 13 bundled checks passed with no skips.
The first package run passed archive/license checks but the external consumer
TypeScript compiler hit its existing 30-second child timeout. The failure log is
retained. An isolated retry with the same timeout passed all three package checks,
including 11 installed runtime checks on each installation. Other lane activity
was not controlled, so contention is not established as the cause. No timeout
or frozen limit was increased.

## P3.3/P12 fresh source composition

Baseline `1f812e02407225c9f8f272651f3aebb2d124433b`. Re-read the complete
current policy/review order and restarted from observation admission and session
ownership. Verified the preceding commit's eight paths, 78 source hashes and nine
reports before publishing it to PR #44. The single CI snapshot was queued/behind
at `8ade520`; no polling or check bypass. The earlier compiler timeout remains
negative evidence despite its unchanged-timeout retry passing.

The source review followed admission/lease projection, bounded session and wire
parsing, shared transport cleanup, generated contracts/validators, packed consumer
allowlists, the actual-service harness, P12 presentation and page lifecycle, and
browser packaging. Their existing separation remains appropriate: transport
admission runs in executable client code; P12 renders fixed text from admitted
aggregate views and does not confer source authorization or current presence.
The Python harness still starts the existing service test fixture and executes an
installed Node consumer; it is not deployed client code or a second server. No
new language migration winner or changed producer contract was established in
these source inspections. Historical component decisions are evidence inputs;
this record does not assert full phase or product qualification.

A concrete interoperability gap remained between two built components: the SDK's
`observe()` callback returns snapshots, while `mountObservationHost` requires
fresh `view()` and `disconnect()` methods. Saving callbacks would bypass read-time
expiry and revocation. Seven missing-export regressions preceded the new
`createObservationSource()` implementation. It exposes only a typed fresh view,
disconnect and explicit asynchronous start. Both source and legacy callback API
reuse one private transport function and the same decoder, session validator,
schema admission and aggregate lease. The source has no display callback cache,
extra timer, public accept method, retry or queued start.

One private run owns its Observation and abort controller. Disconnect detaches it
before aborting; fresh reads check both run identity and cancellation before
returning. A separate busy gate rejects overlapping starts until the prior
promise, including independent best-effort deletion, settles. This avoids a new
session being cleared by an older cleanup. Explicit restart is possible afterward.
A host-clock reentry test exposed a missing second cancellation check in the
initial implementation; its failing result is retained and the check is now
executed after reading the observation. This is a controlled host reentry case,
not a claim about ordinary native clock behavior.

SELECT TypeScript/native closure ownership for this composition. Fresh research
compared direct typed host APIs, checked ECMAScript, tagged RxJS Subscription,
Kotlin/JS and ReScript external bindings. The decisive requirement is one fresh
pull reader with one owned asynchronous run, not reactive fan-out, cached replay,
or shared JVM code. Alternatives still need the same explicit admission/expiry
and host abort rules. No measured cross-language speed ranking or installed-tool
preference is claimed. The [closed source ADR](../../../examples/clients/typescript/source-adr.json)
records constraints, primary sources, candidate tradeoffs and four C4 views.

Public declarations and external installed-consumer checks cover the new factory.
The browser bundle exports it using the same closed dependency graph. A structural
DOM integration mounts the host first, admits a wire observation, hides the page,
checks immediate display withdrawal and transport abort, and confirms restoration
does not authenticate again. A bundled case rechecks cancellation during a host
clock read with string code generation disabled. The containing product still
owns permissions and any explicit restart decision. Existing expiry/byte limits,
current UNKNOWN semantics and versioned wire interfaces remain unchanged.

[Composition evidence](evidence/phase3/p33-source-composition-v1.json) retains
missing-component and reentry failures alongside focused transport, browser and
packaging verification. Native browser lifecycle/keyboard and installed-product
acceptance, release-bound role-aware P19 help, and the producer payload/whole-event
cap discrepancy remain open. No completion marker is created. Next earliest
unreviewed component: the containing browser connection/error flow and its
contextual help inventory against the now-executable fresh source interface.

The previous ReScript `/manual/latest/` link returned the generic landing page.
The current function-binding manual was retrieved and both the new source ADR
and existing lifecycle ADR now link to it. This corrects source attribution only;
no framework performance claim or prior test outcome is retroactively changed.
Final focused verification passed 205 SDK checks, 50 operator checks, 14 bundle
checks and all three package lifecycle checks. The externally installed and
reinstalled archive each passed 12 runtime checks, including the new factory
surface; public declarations compiled against the installed package.

### Callback publication re-review after source composition

Fresh inspection began again at P3.3 Observation, wire/session admission and the
shared observer. The pull source rechecked cancellation after clock access, but
the older callback path checked too early: cancellation from an admission clock,
stream view clock or timer view clock could publish one cancelled projection.
Three focused failing assertions reproduced these controlled host interleavings.
A shared publication function now constructs a fresh view, rechecks renderer
lifetime and native abort state, and substitutes a cleared expired UNKNOWN view
before invoking the callback. The empty replacement uses an explicit clock value,
so withdrawal does not call the host clock again. Callback exceptions still use
the existing cleanup/error path; wire limits, privacy projection and API signatures
are unchanged.

KEEP TypeScript/native APIs with this correction. The current comparison includes
checked ECMAScript, tagged RxJS takeUntil, Kotlin/JS and ReScript. All compile-to-JS
alternatives still need explicit ordering around host calls; reactive completion
does not by itself guard arbitrary callback side effects. No cross-language speed
ranking is claimed. The [closed ADR](../../../examples/clients/typescript/render-publication-adr.json)
records constraints, source-bound tradeoffs and four C4 views.

[Verification evidence](evidence/phase3/p33-render-publication-v1.json) retains the
three failures and focused results. Native browser acceptance and the containing
connection/error UI with release-bound role-aware help remain open. This correction
precedes forward UI expansion; no lane or technology-audit completion is asserted.

Final focused results: 78 SDK checks (including four closed ADR checks), 50
operator checks, 15 no-string-code-generation bundle checks, and three package
lifecycle checks pass. Install and reinstall each execute 12 runtime checks.
The first package invocation incorrectly bypassed npm; two entry-point guards
failed before packaging, and the corrected documented invocation passed. Both
logs are retained. Historical browser probe and earlier compiler timeout evidence
remain unchanged. The new publication ADR refines the earlier timer decision's
check ordering; its earlier C4 diagram is a historical record, not the current
publication sequence.

## P12 explicit connection controls and local guidance

At baseline b85429be47e8c69294e40397f174cee8c2e0a99d the callback-publication
bridge commit, eight exact paths, 83 source hashes and eight report hashes were
verified before publication. Fresh review restarted with Observation, wire/session
admission and shared transport, then inspected the presenter, panel, lifecycle
source boundary and browser builder. Existing cancellation fixes and UNKNOWN
projection remained consistent with those sources. No new migration winner for
those boundaries was established; prior qualification limitations remain.

The next concrete integration gap was an absent explicit connection UI. A caller
could compose the SDK and display, but there were no reusable Start/Stop controls
or local opening/failure/cleanup guidance. Ten missing-module assertions preceded
this bounded component. The initial compiler rejected a control-flow-narrowed run
type; an explicit Run type corrected it without weakening compiler options. Both
negative logs are retained.

SELECT native HTML with TypeScript for two controls, one pending operation and
synchronous withdrawal. Current official HTML, Lit lifecycle, Elm interop and
ReScript binding documentation informed the comparison; checked ECMAScript is
also considered. No custom-element registry, reactive render loop or separate
application runtime is required by this host boundary. No native-speed or
cross-language benchmark claim follows. [Connection ADR](../../../examples/operator/connection-adr.json)
is closed-schema checked and supplies the C4 views.

The new component starts disabled, permits one explicit host operation, and has
no transport code, credential fields, storage or timer. Its owned AbortSignal and
host disconnect callback implement Stop, permission withdrawal and page lifecycle
withdrawal. Restart stays gated through cleanup and always needs a new click.
A failed source withdrawal latches the control unavailable. The host and backend
still enforce authorization; enabling a button is not an authority grant.

All seven states carry local English/Swedish help topics, and both buttons carry
stable feature IDs. Tests cover each state/locale, host failures, reentry, pending
cleanup and actual SDK/display composition. The browser allowlist adds only the
new compiled control module. This is a reusable component, not the completed
integrated application or P19 release-bound help inventory. Remaining work includes
unified language/account integration, full help inventory/search and native-browser
acceptance. [Source-bound results](evidence/phase3/p12-connection-controls-v1.json)
preserve negative evidence. No audit-complete marker is created.

Final verification passed 66 operator tests (16 connection-specific tests) and
16 bundle tests with string code generation disabled. The failed-build recovery
reproduced every artifact byte. The manifest verifies ten compiled runtime inputs
and four distributed artifacts. Syntax and diff checks pass. These are local
software checks; the two earlier Chromium probe failures remain retained, and
no native-browser or customer acceptance claim is added.

## P12 containing client: one locale and explicit observation availability

Baseline `56f0bdc7ee3832e2ed8c088ed412615df3fa4916`. The controller's commit,
12 changed paths, noreply author/committer, 88 source hashes and seven report
hashes were checked before publishing that baseline to PR 44. The source review
restarted at the contract generator and admission, then read bounded wire/session
parsing, Observation, shared transport, source ownership, presenter, panel,
lifecycle, connection controls and the browser builder. No frozen schema or
lease was changed. Forty-four focused generator/admission/wire/session/source
checks pass on this baseline's unchanged SDK sources.

| Component | Current decision and evidence boundary |
| --- | --- |
| Contract generator and standalone validators | KEEP ECMAScript generation and AJV standalone admission. Current official AJV standalone, Kotlin/JS and Dart interop references confirm runtime validation remains necessary across these alternatives. Generated drift and independent negative cases execute; no new runtime compiler or parallel schema definition is warranted. |
| Bounded wire/session and observation ownership | KEEP native byte buffers and TypeScript/ECMAScript. Input byte/depth/numeric bounds, copied aggregate state and revocable fresh views remain exercised. ReScript/Kotlin/JS bindings would retain the same native byte/Fetch boundary; no material replacement is established. |
| Transport and source lifetime | KEEP shared Fetch/AbortSignal implementation and single pending source. Review confirms fixed errors, redirect rejection, rechecked cancellation and independent best-effort cleanup. A callback that ignores cancellation remains an explicit host-contract limitation. |
| Native presenter, panel, lifecycle and connection controls | KEEP synchronous native DOM boundary. FIX composition gap below. ReScript bindings, Elm ports and Lit lifecycle remain credible choices for broader applications; none removes the required synchronous source-withdrawal obligation at this small boundary. |
| Browser packaging | KEEP pinned esbuild development-only bundling and closed runtime allowlist. Actual failed-build recovery, artifact hashes and no-string-code-generation import are checked. This is a browser component artifact, not a signed customer distribution. |

Current official source refresh: [AJV standalone](https://ajv.js.org/standalone.html),
[Kotlin/JS interop](https://kotlinlang.org/docs/js-to-kotlin-interop.html),
[Dart interop](https://dart.dev/interop/js-interop/usage),
[esbuild API](https://esbuild.github.io/api/), and the TypeScript/ReScript/Elm/Lit
references in the closed [client ADR](../../../examples/operator/client-adr.json).
These are interoperability/property comparisons, not cross-runtime speed rankings.
No incumbent is retained on installed-tooling or familiarity grounds.

The concrete gap: callers previously had to coordinate observation and connection
locales and implement immediate display refresh on access withdrawal themselves.
Eight missing-component assertions preceded `mountObservationClient`. The new
composition owns one root, keeps both panels and help in the same locale, and
reads a source only during an explicitly started enabled session. It revokes its
local read gate before adapter cleanup and refreshes even if cleanup throws.
Reentrant withdrawal cannot republish an older read; enabling again cannot revive
an earlier observation. Three-argument panel/host consumers retain local language
selection; an optional request callback supports the containing locale owner.

Validation: 76 operator tests (including ten new client tests), 17 bundled tests
with string code generation disabled, and 44 focused SDK tests pass with zero
skips. Browser tests include byte-identical failed-build recovery. Eleven compiled
runtime inputs produce one self-contained module plus licenses and unsigned hash
manifest. TypeScript, JavaScript syntax and diff checks pass. The eight initial
missing-component failures remain in the source-bound evidence. No native browser,
physical or customer acceptance result is inferred from these checks.

[Evidence](evidence/phase3/p12-client-integration-v1.json) binds current sources,
logs and built artifact hashes. Full role-aware release-SHA help inventory/search,
onboarding, accounts and independently installed product acceptance remain open;
the next executable slice is the source-derived contextual help inventory. The
producer whole-SSE-event boundary handoff and earlier negative evidence remain
unchanged. No phase, lane, P19 or technology-audit completion marker is asserted.

## P12 state-help extraction and artifact parity

Baseline `321a11b9abc08b7bd9f4197e75c5b25ad5977ff4`. Verified the containing-client
bridge result, fourteen paths, noreply identity, 93 source hashes and six report
hashes before publishing the baseline to PR 44. Restarted review at generation
and contract admission, checking current declaration generation, standalone
validator metadata and their negative tests, then the unchanged bounded SDK
source boundary and P12 presenter/connection state dictionaries, locale ownership,
lifecycle, containing client and build graph. Existing state withdrawal and local
locale behavior remain supported; no replacement runtime materially wins for
these native host contracts on the available evidence.

FIX the missing executable state-help inventory. The UI contained accurate local
state guidance, but no distributed source-derived artifact linked its declared
state sets, translations and actually rendered bundle. Eleven missing-tool tests
preceded the new build-time extractor. It parses the two actual TypeScript source
files, admits literal dictionaries only, and compares them bidirectionally with
the declared state/locale unions. Missing translations, new undocumented states,
extra unshipped topics, duplicate keys, empty text, executable expressions and
malformed source are rejected. There is no evaluation of source expressions.

SELECT ECMAScript with the pinned TypeScript compiler AST for this two-file build
tool. Official compiler API, Tree-sitter and SWC documentation informed current
comparisons with Python/Go grammar bindings, Rust/SWC and ReScript bindings. Exact
compiler-language syntax compatibility and fail-closed literal extraction are
the decisive requirements; no large-tree throughput or native runtime advantage
is asserted. The compiler remains a development dependency outside the eleven
browser runtime inputs. Its pinned API is reviewed again on upgrades. The closed
[state-help ADR](../../../examples/operator/state-help-adr.json) has all four C4
views and records these limits.

The build distributes STATE-HELP.json and hashes it in the artifact manifest.
It binds source bytes, module bytes and Git provenance; dirty builds have a null
release SHA, and a changing HEAD fails the build. A clean revision is unsigned
component provenance, never P19 acceptance. Failed builds remove the help artifact
along with earlier bundle outputs; recovery reproduces all artifact bytes.

Validation: 88 operator checks, including twelve extractor/ADR checks, and 18
bundled checks pass with no skips. The actual standalone module runs all ten
states in both locales without network and opens each native details entry point;
its rendered title/body/topic set must exactly match the packaged inventory.
This catches missing and unreachable extra state topics without a second manually
maintained state list. The focused 44 SDK generation/admission/wire/session/source
checks also pass. JavaScript syntax, manifest hashes and diff checks pass.

This is intentionally the **state-guidance portion** of help coverage. The output
sets product_help_complete=false and lists remaining action-specific topics,
route/role coverage, search/onboarding/manuals and installed-product acceptance.
No account/admin workflows are invented. Native browser and independent customer
acceptance remain open, as does the producer SSE-size contract handoff. The
[source-bound evidence](evidence/phase3/p12-state-help-v1.json) preserves initial
negative results and earlier failures. Next: action-level contextual help and
coverage in the containing client. No completion marker is created.

## P12 button descriptions and action-help inventory — 2026-10-10

Baseline: `286e2df61d3ccf0735c1bf10deaa4b9cd37085a7`. The local controller commit,
98 source hashes and six prior reports were verified before publishing it to PR
#44. The single check snapshot still showed queued checks on `321a11b`; no CI
polling or merge was attempted.

The review restarted at the P3.3 generator, standalone validator and wire/session
admission boundary, then revisited aggregate ownership, cancellation, source and
P12 presenter/panel/lifecycle/connection composition through the browser builder.
The reviewed guards still reject ambiguous data and withdraw unavailable state.
The producer whole-event/payload size mismatch remains a peer-owned contract gap.
No frozen time/resource threshold or peer implementation was changed. Existing
scope limits and negative evidence remain applicable; no full-lane completion is
inferred from the prior audit.

FIX the four shipped buttons' missing action-level help. English, Svenska, Start
and Stop now have visible fixed descriptions in both locales, short button names,
unique `aria-describedby` links and stable feature IDs. The shared locale owner
updates descriptions without starting a session. Stop's wording describes local
withdrawal and requested cancellation, not confirmed remote removal. Description
IDs identify DOM elements only. Disposal clears text and removes the links.

KEEP TypeScript/native DOM for this synchronous text-only presentation boundary.
The fresh domain comparison includes Lit custom elements, ReScript DOM bindings
and Rust/wasm-bindgen: declarative custom-element lifecycles, a second typed JS
binding boundary or Wasm memory/DOM interop do not materially address a missing
requirement for four native controls. No throughput ranking is claimed. Official
sources and all four C4 views are in the closed
[action-help ADR](../../../examples/operator/action-help-adr.json).

The build-time AST extractor now also emits `ACTION-HELP.json`, separately
versioned from state guidance. Exact action/locale parity and literal text are
required. The source hash, actual module hash and clean/dirty Git binding travel
with the inventory and are included in the unsigned manifest. Tests traverse
every real bundled button in both locales, resolve its description, compare text
and labels, and execute all four actions offline. This detects new undocumented
buttons, unused topics, language drift and broken contextual links. Full product
help is explicitly incomplete; native browser/screen-reader and independent
installed-product acceptance still require evidence.

Seven initial missing-help/inventory failures were retained before implementation.
A subsequent refresh-identity test caught unnecessary text-node replacement;
conditional updates now preserve unchanged descriptions during refresh. Its
initial failure is retained alongside the final regression check.
Final counts and exact tested source/log/artifact hashes are in the
[action-help evidence](evidence/phase3/p12-action-help-v1.json). No audit completion
marker is created. Next: evaluate a bounded offline help-search contribution over
the implemented public topics, while preserving role-sensitive product-help gates.

## P3.3 locked offline consumer and CI repair — 2026-10-10

Baseline: `bfc2124938ff97c505d59ab3a8352e379bd0638a`; the controller commit,
103 source hashes and seven prior reports were verified before publication to
PR #44. Review restarted at generator/validator, wire/session boundaries and
package delivery. The planned P12 help-search expansion was suspended when the
single continuation snapshot exposed packaging and formatting failures.

FIX the earliest demonstrated packaging mismatch: preparation with `npm ci`
caches dependency archives but need not cache registry packuments. The unlocked
external `npm install <archive> --offline` used by the package test and production
service smoke required that metadata. Hosted Linux and Windows therefore failed
with `ENOTCACHED` for AJV. Linux's packed-client run tested merge revision
`2078c318f56f2ae51f74d00d40c143fc85ec98bf`, composed from PR head `286e2df` and
base `fce89d3`. The two development failures reported three unformatted lane-owned
smoke files; those files are now formatted with the pinned Ruff 0.16.10.

The shared local `offline-consumer.mjs` adapter projects the committed npm-v3
runtime graph and the actual archive SHA-512 into an external consumer lock.
Both consumers call `npm ci --offline --ignore-scripts`. npm validates dependency
satisfaction/integrity, rather than this adapter inventing a resolver. Unsupported
formats, missing pins, links and dependency declaration drift fail closed.
Uninstall is still exercised; same-version reinstall restores the generated lock.
No network fallback, package-check removal, weakened timeout or threshold change.

KEEP ECMAScript for this build/test boundary after comparing Python JSON/hashlib
and Rust/Serde. The actual consumers must execute Node/npm on Linux and Windows;
a single JSON/crypto adapter avoids adding Python to the standalone Node package
suite or a native executable without a demonstrated performance requirement.
KEEP Python for the existing HTTP-service orchestration through this versioned
JSON boundary. The closed [decision](../../../examples/clients/typescript/offline-consumer-adr.json)
records primary sources, deployment constraints and all four C4 views.

Verification uses an isolated cache containing only the five integrity-checked
runtime archives, with no registry metadata. The old unlocked install is expected
to fail; the locked install passes public type checks, twelve installed-runtime
checks, uninstall and locked reinstall. Forty-nine focused SDK checks and sixteen
controlled smoke checks pass. The actual production-service smoke built, packed,
installed offline and returned three delayed-display callbacks with current
conditions UNKNOWN. Source/archive binding was verified. Three-file Ruff lint,
format and diff checks pass; Windows repair still requires hosted verification.

Preserve the hosted failure logs, four missing-helper failures, formatting RED,
and an initial local smoke rejection caused by package source edits while it ran.
That provenance rejection was correct; the final stable-input run passed without
relaxing the check. [Evidence](evidence/phase3/p33-offline-consumer-v1.json) records
exact source/log hashes and the retained production-service result. No browser
suite rerun is claimed for this build/test-only correction. Broader P12 review and
help-search work remain next; no full-lane or P19 completion marker is created.


## Fresh earliest-component review: generator selectors

Baseline `c3ca1e8cb7229db29b64a9c0960e6d8728cdf91e`. Re-read the declaration
generator, standalone validator builder, generated outputs and packaging boundary.
Found an executable mismatch: early return from `$ref`, `const`, `enum` and
`anyOf` could ignore sibling assertions or emit malformed empty unions. Twelve
negative cases failed on the baseline. Explicit selector guards now reject them
with the existing fixed error; scalar literals must agree with their optional
type and enum values must be unique. Published API-v1 generated bytes remain
unchanged. Runtime validation still enforces bounds that TS types cannot express.

[Component decision](../../../examples/clients/typescript/generator-selectors-adr.json)
records constraints, current official sources, four alternatives and all four C4
views. KEEP ECMAScript for the narrow build projection; FIX selector handling.
OpenAPI TypeScript and quicktype offer wider generation; Rust typify emits Rust
types. None removes this component's requirement for an explicit closed contract
guard. This is an output/semantics decision, not a performance ranking. The test
checks byte equality and rejection behavior; alternative compilers were not run.

No full schema-validator or audit-completion claim is made. Next earliest review
is the remaining generator structural forms and standalone validator boundary,
before returning to later client and help components.


## Fresh structural generator and validator boundary review

Baseline `5c52aef4c04f9048b231c1c680d562f2c8606568`. The earliest component
review confirmed prior selector rejection, then found generic shape checks still
missing: string/duplicate required lists, malformed array and scalar bounds,
undeclared required fields and foreign structural keywords could emit output or
raise incidental errors. Fourteen new baseline failures are retained.

MIGRATE generic keyword-shape validation to local AJV Draft 2020-12 metaschema
validation; KEEP ECMAScript projection and explicit subset guards. This corrects
production build code now. The [closed decision](../../../examples/clients/typescript/generator-structure-adr.json)
compares handwritten checks, AJV, Python jsonschema and Rust jsonschema from
official sources, with four C4 views and explicit limits. No foreign runtime
benchmark is claimed. Valid generated files remain byte-identical. Optional
properties and runtime-only string/number bounds have positive contract coverage.

Re-read the standalone validator builder and its 682-case parity corpus plus
14 independent negative cases. Runtime imports still use emitted code, with no
instance schema compilation. A successful build does not make schema shape
checking an authorization or hardware qualification boundary. The remaining
standalone-build failure/artifact lifecycle is the next earliest review item.
No full retrospective audit or lane completion is declared.


## Fresh validator/build artifact lifecycle review

Baseline `ba2f8885b4bbb6844c6b462527b99066c70921b5`. Re-read generator admission,
validator emission, npm build ordering and TypeScript output configuration.
Found stale-distribution behavior: contract drift leaves prior dist intact;
compiler errors can emit files; direct validator parse failure leaves the old
validator. Two package-build and one direct-generator baseline regressions
reproduce these failures.

KEEP Node tooling; FIX generated-output ownership with a sequential Node wrapper,
fixed argument arrays, per-stage 30000 ms timeout, initial cleanup and handled
failure cleanup. Enable noEmitOnError as an additional compiler guard. Direct
validator generation clears only its output before work and after failure.
[Closed ADR](../../../examples/clients/typescript/build-lifecycle-adr.json) compares
Node, shell chaining, Python subprocess and Rust process APIs with current
official sources and all four C4 views. This is a build lifecycle correction,
not a timing or availability qualification. No foreign runtime benchmark.

Fixtures copy only package sources/configuration and the versioned contract,
link local dependencies and run real build stages; no full clean clone. Recovery
checks compare every emitted file with the current successful distribution.
An initial npm exec invocation tried offline Node resolution before running tests;
that negative tooling result is retained separately from the real regressions.
Next earliest review: wire/session admission and observation lifecycle.


## Fresh wire/session byte-admission review

Baseline `ac9fa6984d915f06b775d51b81c2f049ea01f360`. Re-read the earliest
contract generator, validator builder and build wrapper before reviewing wire
and session admission. The preceding bridge commit matches all 22 recorded
source hashes and eight retained report hashes. Native session accumulation and
wire parsing preserve bounded bytes, duplicate-key rejection, strict UTF-8 and
fixed errors. The producer JSON-only cap versus consumer complete-event cap
remains a rejected interoperability fixture and producer handoff.

No production admission defect was demonstrated. Added nine independent session
regressions covering exact fragmented multibyte byte limits, malformed scalars
whose replacement text would match the requested profile, valid Unicode without
normalization, reader release and transport failure after an otherwise valid
JSON prefix. All nine pass on the baseline. A reproducible copied-module mutation
driver rejects nonfatal decoding (five expected failures) and a one-byte cap
increase (one expected failure); it never changes production source or dist.

[Closed component decision](../../../examples/clients/typescript/session-boundary-adr.json)
compares TypeScript, plain ECMAScript, ReScript and Rust/WebAssembly using current
primary sources, with four C4 views. KEEP TypeScript and native host byte/stream
primitives: alternatives do not remove the host admission boundary, and no
measured throughput or native-core requirement establishes a migration benefit.
Static types do not enforce runtime security. No alternate-runtime benchmark,
full memory bound, hard real-time or browser/device qualification is claimed.

The initial package rebuild and one unchanged retry failed with
`client_build_failed` before the focused suite. Their stage cause is absent from
the logs; both failures are retained. A diagnostic invocation of the same wrapper
passed all three stages with unchanged limits (compiler: about 23.6 seconds).
The resulting ten distribution files match the preceding verified build bytes.
All 126 focused tests and public type checks pass. The first packaging invocation
used the read-only default npm cache and failed; the corrected invocation uses
the existing writable lane cache. All three packaging checks then pass. See [byte-bound evidence](evidence/phase3/p33-session-boundary-v1.json)
for the final checks and retry outcome. No threshold was changed. Fetching main
was also refused by read-only Git metadata; the stored origin/main snapshot is
not a freshly fetched head. Next earliest review is session cancellation and
observation lifecycle, before remaining P12/UI/help work. No lane-completion
marker is created.


## Fresh cancellation and observation lifecycle review

Baseline `7f727087180f81c9d016b8d972e4068ba4a9279f`. Re-read the earliest
contract/build and byte-admission components, then traced session creation,
native Fetch cancellation, observation expiry/copying, source revocation,
renderer failure and independent viewer deletion. Verified the preceding bridge
commit against 20 source hashes and 11 report hashes.

Found a verification defect: native caller-cancellation tests could pass after
their cleanup watchdog forced a socket error. A copied POST implementation with
its fetch signal removed passed the original selected test. The mutation audit
correctly failed that false success before the test was changed. Native tests now
reject any watchdog activation, while retaining the original five-second bound
and cleanup. Copied POST and GET signal-loss variants each fail the watchdog
assertion. Production transport and observation code are unchanged.

The [closed component decision](../../../examples/clients/typescript/cancellation-oracle-adr.json)
records current primary-source comparison of TypeScript/native Fetch, plain
ECMAScript, Kotlin/JS and ReScript plus four C4 views. KEEP the direct host
cancellation boundary; FIX the test oracle. Alternative language promises or
bindings do not establish request cancellation. No alternate-runtime speed claim
or production defect is inferred from the mutation result.

Focused lifecycle checks cover fixed error disclosure, native request abort,
unused-body cancellation, clock rollback, expiry, copying, reentrant admission,
source disconnect and busy/restart gates. Source-bound final counts and negative
evidence are in [the review record](evidence/phase3/p33-cancellation-oracle-v1.json).
Next earliest component: endpoint/redirect admission and package/service consumer
lifecycle, followed by remaining P12 display/help review. The SSE event-size
producer handoff, browser/device qualification and P19 gaps remain open.


### Endpoint/redirect and offline lock review — 2026-10-10

Re-read the earliest generator, build, wire/session and observation sources at
`7368b197466796688fc9b8c43a56095ff8fd5b89`; prior source, report and distribution
hashes were verified. This continuation reviewed canonical endpoint admission,
all three authenticated redirect policies, and the shared offline lock adapter.

KEEP native URL/Fetch and the Node lock adapter under the
[transport/install decision](../../../examples/clients/typescript/transport-install-adr.json)
and its closed schema. The decision compares typed JavaScript alternatives and
Dart/Python build adapters against actual host and offline consumer constraints.
No foreign-language benchmark or target-device qualification is claimed.

FIX: the lock adapter classified entries before validating their shape. A null
record produced an uncontrolled TypeError, and seven non-boolean dev markers were
accepted. Thirteen added input/ownership regression methods reproduced eight
failures before correction. Validate records and optional boolean dev markers
before filtering; preserve the valid locked graph and archive integrity binding.

Endpoint/redirect production code needed no correction. Added bounded copied-module
controls independently change POST, GET and DELETE to follow redirects. Each must
fail precisely its ten loopback redirect cases at the destination-I/O assertion;
its other twenty cases and the direct request control must still pass. The audit
runs through npm test, never modifies production/dist, and rejects child timeout,
syntax/import errors, skipped tests and unrelated failures.

The focused Node suite passed 98 methods with no skips; the controlled Python
service-harness suite passed 16 methods. These harness tests use substituted
package/server boundaries and do not establish a new real-service qualification.
The first package check passed two methods but timed out at external consumer
TypeScript compilation under the unchanged 30-second subprocess bound; preserve
that failure separately. One unchanged-bound rerun passed all three package methods,
including external type/runtime use and offline uninstall/reinstall. Exact results
and source/log hashes are in
[evidence](evidence/phase3/p33-transport-install-review-v1.json).

Bridge commit `7368b197` was verified and fast-forward pushed to PR #44. Its one
CI snapshot had 35 queued, four running, one success and one skipped check; no CI
polling or merge. This correction still requires its own local bridge commit.
Next: finish service-harness technology reassessment, then resume the remaining
P12 display/help review. The full lane audit, producer/consumer SSE byte-boundary
handoff and P19 installed-product/help gates remain unfinished.


### Service-harness reassessment — 2026-10-10

At `1947a1d6d758cd98acb313790b03ae1fd481b3dc`, re-read the early generator/build
and session admission, then inspected the complete packed-consumer driver,
controlled rejection tests, producing HTTP fixture and hosted workflow. Verified
17 prior source hashes, nine report hashes and ten unchanged SDK build outputs.

KEEP Python stdlib orchestration and the shared Node offline adapter under the
[service-harness ADR](../../../examples/clients/typescript/service-harness-adr.json)
and closed schema. Compare native Python fixture ownership against Node,
PowerShell 7 and Dart orchestration; Python directly owns the already-required
service lifecycle without a new interprocess fixture-control protocol. This is a
source-based deployment decision with executable contract checks, not a language
throughput benchmark or a preference based on installed tools.

FIX the count-only result assertion. Seventeen negative child-result cases
produced 13 failing assertions and four errors before correction. Nine cases
incorrectly accepted a contradictory/malformed result; the remaining cases
exposed assertion, type or JSON diagnostics. A duplicate-aware JSON parser and
explicit exact-field/type/value gate now admit only integer display callback
counts >=3, UNKNOWN and installed_client true. The gate remains active with
Python optimization. Invalid results produce invalid_consumer_result, leave no
success artifact and still tear down the admitted service.

PASS: all 17 controlled harness methods, including the 17-case result regression;
an additional optimized-interpreter run of that regression; and all 20 Node
lock/closed-ADR methods. Python compilation and diff checks pass. The service
fixture is read only in this correction. No SDK runtime, transport bound,
subprocess timeout or immutable capability threshold changed.

The current interpreter has no httpx/uvicorn/starlette/pydantic; no fresh actual
production-service execution is claimed. Controlled npm/server substitutions
verify orchestration and selected actual Node/SDK paths, not physical or installed
customer acceptance. The report does not authenticate hostile local executables
or attest every producer/toolchain dependency. Retain the full source/log evidence
in [this result](evidence/phase3/p33-service-harness-review-v1.json).

Verified bridge commit 1947a1d6 was fast-forward pushed to PR #44. One snapshot
reported 37 queued, two running, one success and one skipped check; no waiting,
polling or merge. Next earliest unreviewed component: P12 display presenter/panel,
then lifecycle and help coverage. Full lane and P19 completion remain unclaimed.


### P12 presenter, panel and direct build reassessment — 2026-10-10

At `b356d7c6b53865235b95cfe08c3c420da85dfea3`, re-read the authoritative
policy and V3 order, checked the early SDK evidence and verified all 13 previous
source hashes, six report hashes and ten SDK outputs before editing. Re-read the
P12 presenter/panel implementation, tests, schemas, decisions, documentation and
compiler/browser build boundaries.

KEEP TypeScript for the fixed aggregate presenter and native DOM panel. Fresh
comparison against plain ECMAScript, Elm ports, ReScript JSON interop and Lit's
reactive lifecycle still supports the existing scoped decisions in
[the presenter ADR](../../../examples/operator/adr.json) and
[the panel ADR](../../../examples/operator/panel-adr.json). Their decisive constraints
are a synchronous three-state projection, browser/Node ESM, typed host contracts,
fixed bilingual text and explicit host ownership. Runtime shape guards remain
necessary for every candidate; none eliminates the host trust/freshness boundary.
No numeric kernel, alternate-runtime speedup or new application framework is
justified for these two components. This comparison is source-based, not a
cross-language benchmark.

Confirmed UNKNOWN current state, finite shape-only uncertainty validation,
withdrawal on malformed projections, literal text rendering, stable native
controls, latest-refresh precedence and disposal. Covariance shape admission is
not physical accuracy validation. The early clone has no pre-clone memory bound.
Native DOM/LinkeDOM tests do not establish assistive-technology or real-browser
acceptance; previously failed browser probes remain negative evidence.

FIX direct operator compilation: its npm build entry previously invoked tsc
without noEmitOnError or cleanup. A real-compiler regression failed because the
rejected build retained stale/partial dist files. The Node wrapper now clears its
owned output before compilation and after child failure; the compiler suppresses
emission on diagnostics. Separate arguments, the absolute running Node executable,
no shell and a requested 30-second compiler timeout constrain this build boundary.
Retain detailed spawn-error causes and nonzero exit/signal diagnostics. No host
runtime behavior or immutable observation threshold changed.

The new closed [build ADR](../../../examples/operator/build-adr.json) includes
four C4 views and compares Node with POSIX shell, PowerShell 7 and Dart. KEEP the
Node compiler host: the required process/filesystem controls need no additional
interpreter, binary or deployment contract. This is a build-tool decision only.
Cleanup does not cover forced wrapper termination, host crash, concurrent writers
or filesystem failure; direct tsc and the separately owned browser bundle retain
their documented distinct lifecycles.

The first full compile failed with the initial generic diagnostic and correctly
removed dist; its exact child cause was not retained. Preserve that result. One
retry at the unchanged timeout passed, with all 14 generated files byte-identical
to the pre-change output. Final focused test results and source/report hashes are
in [the evidence](evidence/phase3/p12-display-build-review-v1.json). No full repository,
clean-clone, actual-browser or customer-install qualification was run.

Verified bridge commit b356d7c6 was fast-forward pushed to PR #44. Its one exact-head
snapshot showed 40 queued and one skipped check; no polling or merge. Next earliest
unreviewed component: P12 lifecycle scheduling and suspension, followed by the
remaining connection/browser/help inventory. Full lane and P19 acceptance remain
unfinished; no audit-complete marker is issued.


### P12 lifecycle host reassessment — 2026-10-10

At `546293e157d98fad61dbfd7c715dd7704d50c6da`, re-read the full authoritative
policy and V3 order, the early declaration generator and current coordination
snapshot, then inspected the lifecycle implementation, test harness, ADR and
host/source documentation. Verified 18 source hashes, ten retained reports and
14 operator output hashes from the previous review before changing documentation.
The stored protected-main ref does not yet contain this lane's lifecycle module;
no peer contract or worktree was modified.

KEEP TypeScript/native DOM events under the updated closed
[lifecycle ADR](../../../examples/operator/lifecycle-adr.json), including its four
C4 views. Constraints remain browser ESM, synchronous source revocation, one
visible-page timer, five event listeners, no queued observations and no added
transport/authentication. Fresh official-source comparison covers plain ECMAScript,
Lit reactive controllers, Elm subscriptions/ports, ReScript bindings and a
worker/message design. Lit connection callbacks do not substitute for page
suspension; a worker cannot own the panel DOM and does not eliminate window
scheduling. No candidate supplies a browser deadline or demonstrated material
advantage for this small source/display boundary. No migration or cross-language
performance claim is justified.

No new runtime defect was found. Three executable cases now cover missed hidden
notifications and explicit reactivation, a late timer callback during suspension,
and failed revocation after the host was already active. The last case remains
unavailable even after the clearer is repaired, until disposal/remount. All 21
lifecycle methods pass, with no skips or cancellations. Tests use a structural
DOM, synthetic events/clocks and a mocked transport around the actual SDK source;
they do not qualify real browser navigation, OS suspension or service operation.

Two isolated negative controls remove timer cancellation and clear the failure
latch respectively. Each fails its selected new test at the intended assertion;
module/syntax errors are rejected as evidence. Controls use copied compiled code
in data URLs, bounded child runs and temporary test files removed in finally;
production source and dist remain unchanged. These are injected failures, not
production defects. Raw scripts/results and source hashes are bound in
[the evidence](evidence/phase3/p12-lifecycle-review-v1.json).

CLARIFY revocation responsibility in the ADR/README: the lifecycle host delegates
to source.disconnect(). A plain Observation clears its local state, while the SDK
createObservationSource also aborts its owned ingress. Neither gives this display
adapter independent authorization or producer-control authority. A requested
20 ms interval remains a scheduling request; stalled/terminated browser execution
cannot guarantee cleanup. This preserves the API, resource bound and negative
browser evidence.

Verified bridge commit 546293e1 was fast-forward pushed to PR #44. Its single
exact-head snapshot showed 40 queued and one skipped check; no polling or merge.
Next earliest unreviewed component: P12 connection controller and browser build,
then the remaining help inventory. Full lane/P19 acceptance remains incomplete.


### P12 connection-controller reassessment — 2026-10-10

At `4c658ce7c1b865a2b55d280f0cc7638c52a5603e`, re-read the authoritative
policy/V3 order and early SDK build boundary, verified eleven prior source hashes,
seven retained reports and fourteen operator outputs, then reviewed connection
source, tests, composed client, ADR and documentation. No peer or native-client
module changed.

KEEP TypeScript/native HTML under the updated closed
[connection ADR](../../../examples/operator/connection-adr.json). Fresh official
source comparison against checked ECMAScript, Lit reactive lifecycle, Elm interop
and ReScript bindings supports this synchronous two-action/one-operation boundary.
The decisive constraints are browser ESM, explicit AbortSignal interop, immediate
source withdrawal, fixed bilingual state text and a typed host lifetime contract.
No alternate runtime removes host authorization responsibilities or establishes
a timing advantage; no migration or cross-language benchmark claim is justified.
The four C4 views now explicitly include the clearing gate.

FIX a reentrant-start defect. When no operation was pending, disconnect could
synchronously enable the controls and dispatch Start while withdrawal was still
executing. Both permission-withdrawal and pageshow reproductions started one
operation before the callback returned, failing the expected zero-start assertion.
The actual begin guard and displayed Start availability now both reject that
clearing interval. Attempts are ignored without queuing; the tests also confirm
a subsequent independent Start succeeds after successful withdrawal. This is
callback-order enforcement, not authentication or containment of hostile host code.

The focused connection/composed-client/lifecycle/help suite passes all 70 methods,
including the two regressions. Eight Node-based artifact checks additionally exercise the
same two cases with a data-URL imported standalone bundle and string code generation
disabled; exact results and hashes are in
[the evidence](evidence/phase3/p12-connection-review-v1.json). Runtime state vocabulary,
localized help topics, public signatures, cancellation semantics and timing bounds
remain unchanged. Only the generated connection JavaScript needs different runtime
bytes; other compiled operator modules are compared against the prior evidence.

Verified bridge commit 4c658ce7 was fast-forward pushed to PR #44. One exact-head
snapshot reported 40 queued and one skipped check; no polling or merge. Next earliest
unreviewed component: the containing P12 client and browser build, then remaining
help coverage. Full lane and installed P19 acceptance remain incomplete.


### P12 containing-client reassessment — 2026-10-10

At `745bf68740efece34fcb1b6a28e8fcb4ef6b8366`, re-read the authoritative
policy/V3 order, verified the bridge commit and thirteen prior source hashes,
six reports and twenty-one compiled/distribution outputs. Reviewed the client
composition, both child lifetimes, locale ownership, source-read epoch, disposal,
public interface, tests, ADR and documentation. Earlier evidence is retained.

KEEP TypeScript/native DOM under the closed
[client ADR](../../../examples/operator/client-adr.json). Browser ESM, direct
AbortSignal interoperation, synchronous local source withdrawal and a single
Promise-owned session are decisive constraints. Fresh official ecosystem research
compares checked ECMAScript, ReScript bindings, Elm ports and Lit lifecycle.
ReScript can bind these callbacks; Elm still requires a JavaScript adapter for
the native session; Lit reactive rendering still needs a synchronous gate.
No measured performance or stronger interoperation result supports migration of
this small boundary. This is an engineering decision, not a cross-language
benchmark. The current ReScript binding page is linked directly; the older
`/latest/` path resolved to unrelated site content during this review.

FIX shared-adapter withdrawal ordering. The display host registers its lifecycle
handlers before the connection controls. During pageshow/resume, its adapter
clearer could synchronously enable and click Start before the connection controls
processed that same event. Each original source and bundled regression invoked
one adapter start instead of zero. A containing-client clearing gate now prevents
that call and rejects recursive adapter clearing. The wrapper consistently returns
a Promise, so denial cleanup occurs after the current synchronous withdrawal.
The first guard-only implementation blocked the start but synchronously reentered
cleanup and latched failure: both later-restart assertions failed. That intermediate
negative result is retained; the final tests require an independent explicit
restart after successful cleanup and settlement.

The view is still revoked before adapter cleanup and refreshed in finally. This
is enforcement of component callback ordering, not authentication or containment
of hostile host code. No peer module, SDK wire contract, current-state vocabulary,
help topic/action, timer threshold, identity feature or physical interface changes.
The four C4 views, runtime interface limits and README describe the shared gate.

All 72 focused client/connection/lifecycle/help checks and ten Node standalone
bundle checks pass without skips or cancellations. The two source and two bundled
regressions cover both denial and later restart. Thirteen compiled operator files
remain byte-identical; only client.js changes. The rebuilt 148568-byte ESM has
twelve admitted inputs and zero external imports. These are structural DOM/Node
checks, not actual browser, screen-reader, service or customer qualification.
Source/artifact hashes are recorded in
[the client evidence](evidence/phase3/p12-client-review-v1.json). One browser rebuild
failed with the SDK wrapper's generic client_build_failed and removed the browser
outputs. The wrapper did not expose the underlying cause; no timeout attribution
or changed limit is justified. The failure log remains alongside the bounded retry.

Verified bridge commit 745bf687 was fast-forward pushed to PR #44. Its single
exact-head snapshot reported forty queued and one skipped check; no polling or
merge. Next earliest unreviewed component: browser build/provenance, then remaining
help coverage. Full lane and independent installed P19 acceptance remain incomplete.


### P12 browser-build/provenance reassessment — 2026-10-10

At `350e39bba445566d383a711b261e5eb4fd7560cd`, re-read the authoritative
policy and V3 order, verified the bridge commit and all twelve prior source hashes,
ten retained reports and twenty-one generated outputs. Reviewed the browser build,
its closed runtime graph, manifest/help binding, compiler sequencing, failure cleanup,
package entry point, tests and public claims. No peer or native client changed.

KEEP the pinned Go/esbuild bundler with Node ESM orchestration under the closed
[browser ADR](../../../examples/operator/browser-adr.json). Fresh official esbuild
loader documentation specifies supplied byte contents; Rollup and Rust/Rolldown
provide credible load-hook alternatives. Rolldown documentation was accessible
this time, replacing the older unavailable-source note. The deciding requirements
are one browser ESM with existing CommonJS validators, no runtime package loader,
a closed twelve-module graph, in-memory output and explicit byte capture. Esbuild
supports that contract with one local loader callback and no additional third-party
plugin. No comparative benchmark establishes a runtime/resource winner and none
is claimed. Native unbundled AJV ESM still needs helper resolution and another
validator-format parity surface.

FIX two provenance mismatches. The old manifest reread runtime files after esbuild
had consumed them. A controlled change after the real bundler returned produced
a manifest hash for the new file instead of the actual bundled input. The build
also read guidance after compilation; a changed guidance source could be packaged
with an older compiled module. Both intended assertions failed, while a stable
control passed. The first fixture attempt failed for a separate setup reason:
a symlinked AJV dependency resolved outside the fixture's admitted graph. That
log is preserved and is not evidence of the production defects; copying the
small helper/package/license files made the intended cases executable.

The build now supplies each admitted module to esbuild from captured bytes and
hashes those same bytes. Guidance text is captured before compilation, checked
after compilation and bundling, and that captured text generates the inventories.
Source drift removes all seven named outputs. The existing manifest format,
source revision semantics and closed runtime graph remain unchanged. This is not
a signed attestation or a compiler/full-source closure: a trusted, exclusive,
stable build workspace is required, and edits reverted between comparisons are
not detected. No hostile build-process isolation is claimed.

Four bounded fixture cases exercise exact consumed-byte hashes, guidance drift at
two build stages and stable artifact/help contracts; the fifth check validates
the closed ADR/C4. These fixtures use the real build entry point and pinned
esbuild with copied compiled modules; compilation alone is stubbed to isolate the
provenance boundary. They are included in the package test command. README now
lists all eight actual public exports and both distributed help inventories.
The full component build succeeds. All five provenance/ADR checks and all 23
standalone artifact checks pass, including failed-build withdrawal and byte-for-byte
recovery. Eighteen prior generated files are byte-identical, including all fourteen
operator compiled files and the 148568-byte bundle. The two help inventories differ
only by source revision metadata; the manifest covers those revised inventories.
Final component-build/artifact results and hashes are in
[the evidence](evidence/phase3/p12-browser-provenance-review-v1.json).

Verified bridge commit 350e39bb was fast-forward pushed to PR #44. Its one exact-head
snapshot reported forty queued and one skipped check; no polling or merge. Next
earliest unreviewed component: state/action help inventory and coverage enforcement.
Full lane/P12/P19 and independent installed-product acceptance remain incomplete.

### P12 help-inventory and coverage reassessment — 2026-10-10

At `6fcc6dcaf39b14298a59bd3cd4f8e64cf9fbe5ea`, re-read the authoritative
policy, V3 order and full P19 specification. Verified the previous bridge commit,
its fourteen source hashes, seven reports and twenty-one distribution hashes,
then fast-forward pushed that commit to PR #44. One exact-head snapshot reported
forty queued and one skipped check; no polling or merge.

Reviewed the two help extractors, the three literal-guidance inputs, closed ADR
schemas, generated inventories, source and packaged-DOM coverage tests, package
entry point and hosted workflow invocation. KEEP the pinned TypeScript compiler
AST with build-time ECMAScript. The constraints are three small compiler-owned
TypeScript inputs, exact state/action/locale parity, no source evaluation and
no compiler in the browser artifact. Fresh official sources in the
[state-help ADR](../../../examples/operator/state-help-adr.json) support the
comparison: the TypeScript API exposes literal/type nodes in the compilation
syntax; Tree-sitter provides C and other language bindings with a separately
versioned grammar; Rust/SWC supports TypeScript parsing; ReScript can bind to the
same JavaScript API. The latter alternatives are credible outside the incumbent
language. No incremental editor, cross-language parser requirement or measured
throughput problem makes them materially better for this contract. No comparative
performance result is claimed. Compiler API upgrades remain an explicit recheck.

FIX a stale coverage claim: STATE-HELP still listed action topics as unfinished
although ACTION-HELP already describes all four shipped buttons. A focused
cross-inventory regression failed on that extra entry. The generator now reports
the same remaining product gaps in both inventories. README and the closed ADR
explain the separate ten-state and four-action coverage without claiming complete
product help. The packaged state test also checks the pair's remaining-coverage
agreement. No browser runtime, transport, permission, state or language text changed.

The AST extraction is intentionally limited to admitted initializers and unions;
it is not proof of arbitrary program semantics or an authorization sandbox.
Later mutations and shadowing require compilation, code review and packaged-DOM
parity checks. Existing artifact tests compare every exercised bilingual state
and actual button, including label/body, contextual link and language; hosted CI
invokes them through the component package test command. Full routes, permissions,
search, onboarding, manuals and independent installed-product acceptance remain
unfinished. Those limits are now explicit in the ADR.

Verification: the intended regression recorded one failure before the correction;
all 22 focused extraction/action/ADR checks now pass. The component browser build
and both targeted standalone bilingual help tests pass, the latter with dynamic
string code generation disabled and unexpected fetch rejected. Eighteen generated
files remain byte-identical, including fourteen compiled operator files and the
148568-byte browser module. Only coverage/revision inventory metadata and its
manifest binding change. Syntax checks and diff whitespace checks pass. Retained
reports and source/distribution hashes are in
[the evidence](evidence/phase3/p12-help-inventory-review-v1.json).

Next earliest unreviewed component: contextual action-help runtime binding and
its accessibility/lifecycle boundaries. The full lane review and P19 acceptance
remain incomplete; no audit-completion marker is created.

### P12 contextual action-help binding reassessment — 2026-10-10

At `96a5fcff8e63c0d10502627a2bd626c49c1b230b`, re-read the authoritative
policy and V3 order and reviewed action-help allocation, fixed bilingual text,
locale forwarding, disposal, component callers, tests and claims. Verified the
previous bridge commit and its fifteen source, five report and twenty-one
artifact hashes. The verified commit was fast-forward pushed to PR #44; one
exact-head snapshot showed forty queued and one skipped check. No polling or merge.

KEEP TypeScript/native DOM for this synchronous, offline four-button binding.
Fresh official sources in the closed [ADR](../../../examples/operator/action-help-adr.json)
support the domain comparison: W3C guidance separates short visible button names
from linked descriptions; Lit supplies a reactive update lifecycle; ReScript can
bind directly to JavaScript functions; Rust/web-sys exposes DOM access through
Wasm bindings. The contract needs immediate DOM mutation and cleanup with no
transport, numerical computation, cross-target data processing or custom-element
registration requirement. The native DOM implementation satisfies those properties
without another scheduler or artifact boundary. No comparative timing benchmark
or assistive-technology qualification is claimed.

FIX a demonstrated tree-scoping error. ID allocation only queried the Document.
An existing host ID inside a shadow root was invisible to that lookup, so mounting
the client created a second element with the same ID as a contextual description.
Both the compiled-source regression and the previously distributed browser module
failed the one-reference/one-element assertion. The correction passes the mount
root to the internal binder and checks its non-composed root tree as well as the
owner document. A detached root's own ID is included, since querySelector only
searches descendants. This follows the documented getRootNode tree boundary;
no global DOM constructor or cross-realm instanceof check is required.

The allocation attempt limit stays 32, and the per-document WeakMap retains only
a number. This is not a hard execution-time limit: DOM query cost depends on host
tree size. The host remains responsible for later ID changes, cross-tree moves
and independently loaded module copies composing previously detached trees. No
observation identifier, permission, transport or localized guidance text changes.
README and the ADR now state those limits. Tests cover document/shadow/detached
host collisions, exhaustion before mounting and after the display timer starts,
bilingual bundled references and clearing retained descriptions on disposal.

Verification: retained source and old-bundle negative logs each contain the
intended duplicate-ID failure. The first focused panel/connection/client/help
run passes all 59 checks. After adding detached-root-self and partial-mount
exhaustion cases and revising the closed ADR, the final 27 help/inventory checks
pass. The component compiler and browser build pass. Three targeted bundled help
checks pass with dynamic string code generation disabled, including unchanged
bilingual topic parity and the new shadow-root/disposal regression. All twelve
manifest input hashes and six artifact hashes match; external imports remain
empty. Syntax and diff checks pass. Evidence is retained in
[the result record](evidence/phase3/p12-action-binding-review-v1.json).

Next task: reconcile the full P3.3/P12 component inventory and remaining delivery
and integration gates against the corrected HEAD before forward expansion. This
slice closes the contextual action-help runtime review; it does not declare the
full phase review, product Help Center or independent installed acceptance complete.


### P3.3 controlled loopback evidence reassessment — 2026-10-10

At `442678030af32adbb4ba23dd6bae2216c1f5002c`, re-read the authoritative
policy and V3 order, verified the preceding bridge commit and retained hashes,
and pushed that commit to PR #44. The one exact-head snapshot showed forty queued
and one skipped check. No polling or merge. The inventory reconciliation found
an unaudited verification weakness in the standalone controlled loopback fixture;
that correction takes precedence over forward expansion. The introductory cursor
also incorrectly said that no P12 operator implementation existed. It now separates
the implemented reusable client from unfinished product and native client work.

KEEP the standard-library Python HTTP fixture; FIX its evidence gates. The closed
[ADR](../../../examples/clients/typescript/loopback-evidence-adr.json) compares
Python, Node native HTTP, Dart HttpServer and Go net/http against the existing
packed-consumer fixture lifecycle, small synthetic workload and report semantics.
The official Python command-line documentation confirms that optimization removes
assert statements. Each alternative can serve loopback HTTP, but none removes the
need for explicit report admission; separate executable servers add a lifecycle
protocol without a demonstrated concurrency or target-runtime requirement. No
comparative timing result, familiarity preference or production HTTP claim is used.

The focused regression recorded twelve failures: eleven contradictory scenarios
were accepted with the fixture compiled at optimization level two, and a fractional
callback count was accepted without optimization. Explicit condition checks now
reject wrong paths, bearer markers, body, request order, report values and a live
thread after teardown. Callback counts must be actual integers, excluding booleans.
The old controlled report is withdrawn before execution; the temporary service-style
report is removed on exit. Valid output remains explicitly labeled as a controlled
fixture, not the production service. SDK and production server behavior are unchanged.

Verification uses actual handler and report-gate code with a substituted driver,
no sockets or npm. Two unittest methods exercise twenty-eight negative subcases
and two positive controls across optimization levels zero and two. Both normal and
`python -O` parent invocations pass. CI now includes both runs and triggers when
these fixture files change. The ADR is part of the existing strict schema tests,
including root and nested qualification-extension rejection. Workflow actionlint,
Python compilation and diff checks pass. Raw negative evidence is retained in
[the source-bound result](evidence/phase3/p33-loopback-evidence-review-v1.json).
These checks do not establish a fresh packed install, production service run,
thread termination guarantee or independently installed customer acceptance.

Next earliest unreviewed work: finish the complete P3.3/P12 source-to-review inventory
and remaining delivery/integration gates. Exact source matches to older evidence
are useful reconciliation inputs, not fresh decisions by themselves. Native client
selection, producer SSE boundary reconciliation, full operator workflows and product
help/acceptance remain open. No technology-audit completion marker is created.
