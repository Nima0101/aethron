# P12 presentation boundary implementation plan

> Execution: inline in the assigned P3.3/P12 worktree; no subagents. The owner
> authorized autonomous scoped implementation. Commit through the lane bridge.

**Goal:** Provide an executable bilingual presentation boundary for the future
read-only operator UI without turning delayed observations into current evidence.

**Architecture and spec:** [P12-001](adr.json), validated by [adr.schema.json](adr.schema.json).
The SDK continues to own wire admission and local expiry. This component receives
its aggregate projection and supplies fixed text/state/help IDs. UI transport,
DOM, roles, authentication and full Help Center are subsequent components.

**Technology:** TypeScript, compiled by the SDK's pinned compiler; no runtime dependency.
Elm, ReScript, plain ECMAScript and Lit were compared in the ADR. Framework and
bundler selection for the UI remains open.

**Constraints:** Current state always UNKNOWN; en/sv-SE only; all malformed input
withdraws details; maximum five unique supported sensors, 32 covariance pairs;
no persistence/IDs/actuation. Fresh SDK view required at render time. No independent
clock, transit bound or authorization claim.

**Review focus:** malformed authority fields, source disclosure, sparse arrays,
locale mismatch, stale render input. Pin these with negative tests and actual SDK
admission/expiry composition; document that old projections cannot attest freshness.

- [x] Add synthetic tests for expiry, delayed state, malformed inputs, copying,
  throwing getters, locale parity and composition with the actual SDK.
- [x] Observe missing-module RED before implementation.
- [x] Implement `presentObservation(input: unknown, locale: Locale): OperatorStatus`
  in `src/presenter.ts`; fixed local text and input guard, no side effects.
- [x] Add sparse-array RED cases and correct hole handling with dense iteration.
- [x] Validate ADR schema, run final focused tests and inspect the final diff.
- [x] Commit the cohesive component (`2f22c34`); retain source-bound evidence and remaining gates.

Ruling: no separate approval pause or subagent review, following explicit owner
execution/no-subagent instructions. Author self-review has less independence than
an external review; hosted checks and final product acceptance remain required.
