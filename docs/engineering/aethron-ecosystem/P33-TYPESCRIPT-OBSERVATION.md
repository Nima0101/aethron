# TypeScript observation boundary

This bounded P3.3 change hardens the existing Node client example before SDK
distribution. It changes no wire schema, core threshold, server behavior or
platform qualification.

## Requirements and technology decision

Observations must expire even when a supplied clock is malformed or rolls back
during a lease. Caller-owned input and returned arrays must not be able to change
an accepted observation's lease, state, provenance or uncertainty. Transit remains
unbounded, so `current_state` remains `UNKNOWN`.

Keep TypeScript with the pinned AJV validator and built-in monotonic clock. A
native Rust or JVM boundary would still need JavaScript validation and ownership
handling and adds packaging without addressing an established native bottleneck.
Type-only interfaces cannot validate runtime JavaScript values. No new dependency
or platform module is justified for this change.

Primary references consulted 2026-10-09:

- [W3C High Resolution Time](https://www.w3.org/TR/hr-time-3/): use a local
  monotonic clock; do not equate independent client and edge clock origins.
- [ECMAScript Number.isFinite](https://tc39.es/ecma262/multipage/numbers-and-dates.html#sec-number.isfinite):
  reject non-number and non-finite values without numeric coercion.
- [WHATWG structured cloning](https://html.spec.whatwg.org/multipage/structured-data.html#dom-structuredclone):
  take an owned snapshot, then validate that snapshot; cloning errors must not
  retain an old observation or echo input.

Use finite nonnegative local milliseconds, including fractions. Preserve the
existing inclusive `valid_for_ms` boundary. A backwards render clock clears the
observation irreversibly. A fresh `accept` starts a new local lease; it does not
certify transport freshness, session sequencing or live evidence. Snapshot input
before validation and copy covariance arrays on output. Browser suspend/resume
and physical timing qualification remain separate lifecycle work.

## Regression evidence

Tests in `examples/clients/typescript/test.mjs` cover invalid receipt/render
clocks, rollback within the receipt window, input lease/state/provenance mutation,
returned covariance mutation and fractional boundary preservation. The retained
synthetic blackout fixture supplies the observation; no physical evidence is
claimed. Run `npm test` in that package for the complete focused client suite.

The initial run retained 14 failures and six passes. After the fix, compilation
and all 20 tests passed. The same 20 tests passed with the import changed to the
public package name after installing the packed tarball in a separate consumer
directory. The dependency audit reported zero vulnerabilities. Exact source and
artifact hashes, initial failures and unrun gates are recorded in
[the verification record](evidence/phase3/p33-typescript-observation.json).

Linux revalidation passed compilation, all 20 source tests, all 20 installed
package tests, and the dependency audit. The initial install aborted and the
combined npm test command failed to fork under host resource pressure. The
unchanged compiler and test commands passed when run directly in sequence with
a smaller Node thread pool and heap, as recorded in the verification record.
Full release and platform gates remain pending; these focused checks do not
establish P3.3 completion.

## Renderer failure during teardown

A follow-up client lifecycle regression showed that a throwing final display
callback skipped the session DELETE request. Keep the existing TypeScript/fetch
boundary: a nested `finally` guarantees the cleanup attempt without a new
runtime or dependency. The existing two-second cleanup timeout and independent
abort signal remain unchanged. The regression uses controlled fetch responses
and verifies that callback failure plus caller cancellation still produces an
authenticated DELETE; it is not a live server or hardware qualification.

## Watchdog renderer failure

Timer exceptions escape an enclosing async function's ordinary `try` block.
Two retained counterexamples exercised this while response headers or body data
were stalled. Use the same TypeScript/fetch boundary with a private
`AbortController` and `AbortSignal.any` to combine caller and internal
cancellation. This is supported by the Node 22 client target, needs no new
dependency, and avoids manual cancellation listeners in production. See
[Node's abort signal contract](https://nodejs.org/download/release/v22.15.0/docs/api/globals.html#static-method-abortsignalanysignals).

A synchronous watchdog renderer exception immediately clears the observation and
aborts the event request. The observer promise rejects with that error, the
failed callback is not retried in teardown, and authenticated session deletion
still uses its independent two-second timeout. The caller's controller remains
untouched. The regression controls the timer and HTTP responses; it makes no
network latency or live-device claim.

A further retained counterexample closed the body normally during cancellation;
the observer now preserves the renderer error on that path too. Compilation and
all 24 source and installed-package tests passed; the dependency audit reported
zero vulnerabilities. The successful compile emitted a host thread-allocation
warning, preserved in the verification record.

## Transport session and ordering

Consume the existing API v1 `SceneEnvelope` and `HealthEvent` definitions from
the bundled generated schema. Keep the TypeScript/AJV boundary: runtime schema
validation plus a session-scoped scalar sequence check requires no new runtime,
dependency, generator change, server change or contract fork. The published
[API contract](API-CONTRACT.md) requires increasing sequence numbers within a
transport session; the existing server emits an initial gap at zero.

Bind all events to the handle returned by session creation. Validate before
admission, preserve the last sequence across health/gap view clears, and reject
duplicates, decreases, foreign handles, malformed control events and unsupported
kinds with `invalid_event`. Disconnect immediately on failed admission. A new
observer has its own sequence state; jumps forward are permitted. No transport
check certifies freshness or changes `current_state` from UNKNOWN.

Ten rejection regressions failed before this guard, while the initial-gap and
increasing-sequence positive case passed. Tests use the existing synthetic
scene fixture and controlled transport/clock boundaries, not physical evidence.

The combined client increment passes compilation and all 35 source and installed
package tests. The dependency audit reports zero vulnerabilities. The staged
change retains each earlier failure and its source-bound verification record.
