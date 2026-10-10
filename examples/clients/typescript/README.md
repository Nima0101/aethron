# AETHRON TypeScript observation example

This local package is an executed Node client example, not a published enterprise SDK. It uses generated OpenAPI types plus strict AJV validation generated at build time. Node 22+ is the prepared CI target; run the locked package tests before using another runtime.

```sh
npm ci --ignore-scripts
npm test
npm pack
```

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

From the repository root, `scripts/edge_node_e2e.py` installs the packed artifact outside this package and tests it against a real server. The server and Python client instructions are in [edge usage](../../../docs/usage-edge.md).

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
the redirect. The caller still owns initial endpoint trust and transport security;
this does not restrict arbitrary caller-supplied base URLs or certify TLS/MLS/CNSA.

Unused HTTP response bodies are explicitly cancelled: unsuccessful session creation,
unsuccessful event responses, and all DELETE replies. The client neither reads
these bodies into memory nor waits for their source cleanup to finish. Rejected
cancellation promises are observed without replacing the primary result. Native
fetch cancellation is exercised against stalled loopback responses; this does
not prove termination of an arbitrary source that ignores cancellation, remote
handle deletion, or a production cleanup deadline.
