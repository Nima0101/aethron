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

The named profile uses the `warn` contract in this example. Python's example accepts the other contract names explicitly; application SDKs should preserve the schema enum. `observe()` releases its viewer handle when aborted; the supervisor continues processing. An independent 20ms client timer expires stalled observations. Without a measured transit bound, current state remains UNKNOWN and observations are labeled delayed.

`Observation.accept()` snapshots and validates its input. Mutating that input or a
returned covariance array cannot change later observations. Explicit local clock
arguments must be finite, nonnegative milliseconds; fractions are supported.
Invalid receipt clocks clear the observation and throw `invalid_clock`. Invalid
or backwards render clocks clear it and return expired/UNKNOWN. A new acceptance
starts a new local lease; it does not establish transport freshness.

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
timeout and remains best effort when the server cannot be reached.

The display callback is synchronous. If it throws from the watchdog timer,
`observe()` clears its observation, aborts the event request, and rejects with
that error after attempting cleanup. It does not call the failed callback again
or abort the caller's controller.

The stream accepts only schema-valid scene, health, and gap events for the
session it opened, with strictly increasing sequence numbers. Invalid events
clear the observation and reject with `invalid_event`; health/gap events clear
the view without resetting the sequence check. These checks do not prove transit
freshness, so current state remains UNKNOWN.

The implementation uses authenticated fetch streaming rather than EventSource token URLs. The candidate server rejects Origin headers and cross-origin access; the executed evidence is Node on loopback. Browser deployment needs a separately reviewed same-origin/authenticated TLS integration, and is not claimed from the Node test. No CDN is required.

From the repository root, `scripts/edge_node_e2e.py` installs the packed artifact outside this package and tests it against a real server. The server and Python client instructions are in [edge usage](../../../docs/usage-edge.md).
