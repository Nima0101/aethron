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
| Generated contract admission | Reviewed above; 4 validation tests pass, including 14 independent negative cases |
| Observation projection and local clocks | Reviewed below; host-clock exception correction and claim clarification |
| HTTP/session/stream/renderer lifecycle | Pending full V3 review; in-flight cancellation safety fix retained with four RED-to-GREEN regressions |
| Package distribution and fixtures | Pending full review; focused installed-artifact checks are regression evidence only |
| Android/JVM, desktop lifecycle, P12 operator application | No completed implementation identified in the previous inventory; fresh inventory and justified implementation decisions remain outstanding |

No completion marker is created. The session-response admission slice below
resolves the previously open response limit. Lexical integer-form admission and
producer whole-event versus payload-size reconciliation remain open. Cancellation no longer blocks DELETE, but a source may ignore
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
