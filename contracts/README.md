# AETHRON edge contract handoff

API v1 and frozen sensor protocol v3 have independent version numbers. The edge service implements the exported [OpenAPI](openapi/aethron-edge-v1.json); it is a local candidate, not an endpoint on the public camera PWA. [Fixtures](fixtures/v3/blackout-output.json) are actual core outputs. UNKNOWN and [coasting](fixtures/v3/coasting-output.json) are not observed evidence.

The optional in-process [world-model boundary v1](../docs/architecture/world-model-v1.md)
consumes v3 observations through the same runtime. Its envelope explicitly declares
the supported normalized image frame and host-monotonic clock; unsupported contexts
are quarantined. It adds no metric world transform, persistent identity or actuation.

Swift/Kotlin owners should map nullable fields explicitly, reject unknown enums/fields, preserve uncertainty and distinguish tentative/observed/coasting. JSON integers are bounded to the interoperable 53-bit domain; booleans are never integers. Core IDs are ephemeral and must not enter persistent analytics or cross-camera stores. A DELETE closes only the viewer, not the appliance pipeline.

Fetch streaming carries bearer credentials in headers. No token URL, historical Last-Event-ID replay, CDN, or remote activation is required. Reconnect emits a gap; clear the previous scene. A local monotonic timer clears observations on expiration, suspension or disconnect. Without a measured transit/clock bound, label observations delayed and current state UNKNOWN. No client-specific native code or build cache was changed here.

Generate TypeScript declarations and strict runtime schema with `python3 scripts/edge_generate_types.py`, then run `npm ci --ignore-scripts` and `npm test` in `examples/clients/typescript`. Python uses the same strict Pydantic models. Native implementations should run these fixture/rejection cases in their own authorized lane.
