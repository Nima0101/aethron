# AETHRON TypeScript observation example

This local package is an executed Node client example, not a published enterprise SDK. It uses generated OpenAPI types plus strict AJV validation generated at build time. Node 22+ is the prepared CI target; run the locked package tests before using another runtime.

From the repository package directory (not the installed archive):

```sh
npm ci --ignore-scripts
npm test
npm pack
```

The build first checks that committed declarations and the runtime schema match
`contracts/openapi/aethron-edge-v1.json`; drift fails without rewriting either
file. After a reviewed contract update, run `npm run generate` and inspect the
result before rebuilding. The Node generator supports the current closed API-v1
schema vocabulary, rejects unsupported constructs, and preserves fixed-width
arrays as TypeScript tuples. These declarations do not replace runtime validation.
The former `python3 scripts/edge_generate_types.py` command forwards to the same
Node generator for compatibility; Python is not needed for this package's build.
`npm run test:types` checks valid and invalid tuple assignments.

`Observation.view()` and the `observe()` display callback expose the exported
`ObservationView` union. Its `current_state` is always the literal `UNKNOWN`;
checking `label === 'expired'` narrows the observed state to `UNKNOWN` and the
source/covariance arrays to empty tuples. The delayed branch retains the observed
state and sensor source types from API-v1. These are compile-time descriptions
of the returned view, not runtime authorization or transport freshness checks.
`npm run test:package` also packs and installs the archive offline in an external
temporary project, then compiles a consumer of its public declarations. Prepare
the locked dependency cache first; the TypeScript consumer fixture is never executed.
An additional JavaScript consumer checks observation admission, copying, expiry,
disconnect and the public import boundary with synthetic data. The test removes
the package using `npm uninstall`, checks removal from the manifest, lock and
module resolution, then reinstalls the same archive offline and repeats those
checks in a fresh process. This verifies same-version reinstall, not an upgrade
between releases or removal of state retained by an already-running application.

The build generates `dist/validators.cjs` from the unchanged versioned schema.
Runtime imports do not compile schemas or use string code generation. AJV remains
a pinned runtime dependency for its generated Unicode-length helper. The test
suite compares generated admission decisions with the previous compiler across
a bounded mutation corpus and checks loading with string compilation disabled.
`node audit-validation.mjs` runs a small sequential startup/validation comparison;
its timings are observations on the current host, not platform guarantees. See
the [technology reassessment](../../../docs/engineering/aethron-ecosystem/P33-TECHNOLOGY-AUDIT-V2.md).

Install the resulting `.tgz` in an external Node project. Load an owner-only token file locally; do not put it in a URL or persistent browser storage:

```js
import {readFile} from 'node:fs/promises';
import {observe} from 'aethron-edge-client-example';

const token = (await readFile('token', 'utf8')).trim();
const controller = new AbortController();
process.once('SIGINT', () => controller.abort());
await observe('http://127.0.0.1:8765', token, 'bench', state => {
  console.log(state.label, state.current_state, state.sources);
}, controller.signal);
```

The named profile uses the `warn` contract in this example. Python's example accepts the other contract names explicitly; application SDKs should preserve the schema enum. `observe()` attempts to release its validated viewer handle when aborted; remote deletion is best effort and the supervisor continues processing. An independent client timer requests an expiry check every 20ms; host scheduling delays can postpone that check. Without a measured transit bound, current state remains UNKNOWN and observations are labeled delayed.

`Observation.accept()` snapshots and validates its input. Mutating that input or a
returned covariance array cannot change later observations. Explicit local clock
arguments must be finite, nonnegative milliseconds; fractions are supported.
Invalid receipt clocks, including failure to read the host clock, clear the
observation and throw `invalid_clock`. Invalid
or backwards render clocks, and failure to read the host clock, clear it and
return expired/UNKNOWN. A new acceptance
starts a new local lease; it does not establish transport freshness. Local clock progress
and scheduled callbacks are host assumptions, not a suspend or real-time guarantee.
`disconnect()` clears only the internal projection: it cannot revoke copies already
returned to application code. Aggregate sources and covariance can still reveal
scene information; omitting identifiers does not prove anonymity. Direct
`accept()` calls clone JavaScript input before schema validation and do not impose
a pre-clone allocation bound. Use the byte-bounded stream ingress for wire input.

The accepted state uses native JavaScript private fields. Public property names
cannot overwrite its lease or scene, and ordinary reflection/JSON serialization
does not expose the observation. Only the displayed state, sources, covariance
and local lease are retained after admission; transport handles, track IDs and
geometry are discarded from this observation object. This is encapsulation and
data minimization, not process isolation or guaranteed memory erasure. Failed
input cloning clears any observation admitted by a reentrant input getter.
`node audit-observation.mjs` reproduces the bounded legacy/closure/private-field
comparison; `npm test` includes its deterministic timing trace checks.

Teardown attempts authenticated session deletion even if the final display
callback throws or aborts the caller's signal. Deletion uses its own two-second
timeout and remains best effort when the server cannot be reached. Teardown
clears observations, aborts the event request, requests reader cancellation and
releases its lock without waiting for source cleanup. A pending or rejected source
cancellation cannot hold DELETE or replace the original ingress/render error.
This does not guarantee resource termination for a source that ignores cancellation.

The display callback is synchronous. If it throws from the watchdog timer,
`observe()` clears its observation, aborts the event request, and rejects with
that error after attempting cleanup. It does not call the failed callback again
or abort the caller's controller.

The stream accepts only schema-valid scene, health, and gap events for the
session it opened, with strictly increasing sequence numbers. Invalid events
clear the observation and reject with `invalid_event`; health/gap events clear
the view without resetting the sequence check. These checks do not prove transit
freshness, so current state remains UNKNOWN.

Stream decoding bounds each complete wire event to 65,536 bytes, independently
of fetch chunk boundaries. The supported API-v1 profile uses LF or CRLF, optional
`event: scene|health|gap`, and JSON assembled from all `data:` lines. Named events
must match the JSON kind. Comments do not refresh observations. Duplicate JSON
keys (including escaped spellings), excessive nesting, malformed UTF-8/JSON,
truncated events, and unsupported history/retry fields fail closed. Errors use
`invalid_event`, or `event_limit` for an oversized wire event, without input echo.
This is a strict AETHRON profile, not a general EventSource parser: bare CR and
BOM-prefixed framing are not accepted. No automatic reconnect or event history
is introduced.

Known interoperability boundary: the current producer measures the JSON payload
alone against 65,536 bytes, so its maximum payload plus SSE framing exceeds this
client's complete-event bound. That case is retained as a rejection fixture and
requires producer contract reconciliation; the client limit has not been raised.

The implementation uses authenticated fetch streaming rather than EventSource token URLs. The candidate server rejects Origin headers and cross-origin access; the executed evidence is Node on loopback. Browser deployment needs a separately reviewed same-origin/authenticated TLS integration, and is not claimed from the Node test. No CDN is required.

From the repository root, `scripts/edge_node_e2e.py` builds this package, packs a fresh archive in a unique external consumer directory, installs it offline and tests it against a real server. Prepare Node build dependencies and the existing `build/ecosystem-phase1/npm-cache` first; the smoke command does not download missing dependencies. The server and Python client instructions are in [edge usage](../../../docs/usage-edge.md).
The smoke result counts `display_callbacks`, which can include watchdog renders
of the same observation; it does not count distinct wire events. Every callback
must retain current state UNKNOWN. Only its own cancellation with the SDK's
`stream_unavailable` error is accepted as the expected shutdown. A failed attempt
removes the previous result file so stale success cannot stand in for that run.
Success is written only after server cleanup and repeated archive/input hash
checks. The result includes `archive_sha256` and `input_sha256` for the selected
package sources/configuration and OpenAPI input. These local checks detect stale
archives and ordinary source changes during a run; they are not signed build
attestations, compiler/dependency verification or protection from hostile local
processes. The temporary archive is removed with the consumer directory.


Session creation replies use a local 65,536-byte accumulator limit, strict UTF-8
and duplicate-aware JSON parsing, and the existing closed `SessionHandle` schema.
The returned `source_profile` must match the request. Missing/extra/ambiguous
fields, body read failures and oversized replies reject with `invalid_session`
without echoing response details or using an unvalidated handle. This is a client
admission limit, not a server size guarantee or an upstream allocation bound.
Caller cancellation is still required for a stalled response. An invalid/lost
reply cannot establish remote viewer-handle cleanup.

Authenticated session creation, event reception and deletion reject HTTP redirects,
including redirects within the same origin. A redirect therefore cannot transfer
these requests to a different path or origin. Set the intended endpoint directly;
redirect-based routing is unsupported. A rejected creation/stream redirect rejects
`observe()`; a rejected cleanup redirect leaves deletion unconfirmed and remains
best effort. This uses the host fetch redirect policy, not a check after following
the redirect. The caller still owns selection of a trusted admitted endpoint and transport
security. Endpoint syntax admission below does not certify TLS/MLS/CNSA.

Unused HTTP response bodies are explicitly cancelled: unsuccessful session creation,
unsuccessful event responses, and all DELETE replies. The client neither reads
these bodies into memory nor waits for their source cleanup to finish. Rejected
cancellation promises are observed without replacing the primary result. Native
fetch cancellation is exercised against stalled loopback responses; this does
not prove termination of an arbitrary source that ignores cancellation, remote
handle deletion, or a production cleanup deadline.

Request rejections expose fixed errors: `session_unavailable` during session
creation, and `stream_unavailable` during event request/read failure. Session
body failures still use `invalid_session`. Transport exception messages, causes,
and custom abort reasons are not copied into these errors. Callers can inspect
their own `signal.aborted` to distinguish their cancellation; their signal and
reason are not modified. Application display-callback exceptions retain their
identity and remain the application's responsibility.

Cancellation is checked after each event read and synchronous display callback,
before parsing another event in that chunk. Once a validated handle is known,
cancellation clears the observation and attempts DELETE with its independent
timeout. Cancellation before session admission cannot confirm remote cleanup.
The checks do not preempt synchronous callbacks/parsing or establish a real-time
shutdown deadline; the host fetch implementation must honor its abort signal.

Before constructing authenticated requests, `observe()` requires a canonical
origin string: `https://example.test` or `https://example.test:8443`, with at most
one trailing slash. Plaintext HTTP is admitted only for the literal hosts
`127.0.0.1` and `[::1]`. Use lowercase/ASCII host serialization and omit a scheme's
default port. Userinfo, path prefixes, queries, fragments, whitespace, repaired
URL spellings and numeric loopback aliases are rejected with `invalid_endpoint`
before fetch or display is called. `localhost` is not admitted over plaintext
because this policy avoids name resolution for the HTTP exception. A trailing
slash is accepted and removed before constructing the three fixed API routes.

This deliberately tightens the example's former arbitrary-base behavior; proxy
path prefixes and plaintext LAN endpoints are unsupported. A separately reviewed
TLS deployment can use an HTTPS origin. The checks do not authorize that server,
pin its certificate/address, enforce proxy configuration, prevent an application
from supplying the wrong trusted origin, or replace host networking policy.
IPv6/HTTPS URL admission is covered with controlled fetch; actual socket evidence
here is IPv4 loopback HTTP, not remote TLS or IPv6 qualification.

Wire integer fields require integer JSON tokens within JavaScript's safe integer
range. Decimal and exponent spellings such as `1.0` and `1e0`, including fractions
that round to integers, are rejected before schema admission. This client wire
profile is stricter than JSON Schema's mathematical integer definition and follows
the producer's strict integer model. Decimal geometry remains supported. The
parser requires the source-aware `JSON.parse` reviver executed here on Node
22.23.2; missing token-source support fails closed. `Observation.accept()` receives
already parsed values and cannot recover their original numeric spelling.

The package file list names the ten reviewed build files explicitly. Stale modules,
diagnostics and cache files elsewhere in `dist` are excluded. `npm test` runs a
packing check with synthetic extra files; `npm run test:package` reruns that check
after a build. The archive also includes this README, package metadata and an
unchanged copy of the repository license. This does not inspect the contents of
allowed files or prove build freshness: build and test the exact source revision
before packing. The archive is a runtime example, not a source checkout or a
release qualification artifact.
