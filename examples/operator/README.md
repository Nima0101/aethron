# P12 observation presentation boundary

This is a reusable presentation component, not an operator application. It maps
an SDK aggregate view to fixed English (`en`) or Swedish (`sv-SE`) text and a
stable help-topic ID. All current-state output remains `UNKNOWN`. Delayed
observed presence is explicitly distinguished from current conditions. Malformed
projections discard sensor details and return an unavailable state.

Prepare the locked TypeScript SDK dependencies once, then from the repository root:

```sh
npm ci --prefix examples/clients/typescript --ignore-scripts
npm test --prefix examples/operator
```

Only preparation needs a registry. Tests build the SDK, build this module with
the SDK's pinned compiler, and execute synthetic positive/negative checks. The
presenter itself has no dependencies, network requests, browser storage or timers.
The example package intentionally is not independently published or installed.

Use `presentObservation(observation.view(), locale)` at render time. The presenter
cannot determine whether a previously returned SDK view is stale. Pass its strings
to text nodes, not HTML interpolation. Unsupported locales throw
`unsupported_locale`; there is no silent language fallback. Returned sensor arrays
are detached. Covariance shape is checked but the matrix, geometry, session/track
IDs and source input are omitted from the result. Sensor names do not authenticate
an upstream source or establish calibration/accuracy.

Direct object admission snapshots before validation, like the SDK's direct object
API. This is not a pre-clone allocation bound; use bounded SDK wire ingress for
network data. The fixed states are `expired`, `delayed`, and `invalid`, with topic
IDs `observation.expired`, `observation.delayed`, and `observation.invalid`.
English and Swedish explanations are included, but these IDs do not yet constitute
navigable help links or a complete Help Center. No role or permission system is
implemented here.

Remaining P12/P19 work includes the actual accessible UI, scene/map/replay workflows,
source provenance, authenticated integration, release-bound help coverage and
independent customer acceptance. No browser, hardware, tactical, availability or
security certification follows from these Node tests. See [the ADR](adr.json),
its [closed schema](adr.schema.json), and the [implementation plan](PLAN.md).
