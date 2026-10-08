# OpenAPI plan — not an implemented service

Select OpenAPI **3.1.1** [S29](SOURCES.md#s29), explicitly a stable tooling target rather than a claim about the newest spec. Candidate server stack: FastAPI **0.142.4**, Pydantic **2.13.5**, Uvicorn **0.54.0**, consumer HTTPX **0.28.1**; these were observed in public package metadata on 2026-10-08 [S44](SOURCES.md#s44)–[S47](SOURCES.md#s47). They are not installed/qualified application dependencies in Phase 0. Phase 1 must resolve and audit the complete dependency closure with hashes before adopting them.

## Files to produce in Phase 1

`integrations/edge/aethron_edge/contracts.py` owns closed transport types; `contracts/openapi/aethron-edge-v1.json` is the exported reviewed contract; `contracts/fixtures/v3/` contains accepted/rejected bytes and actual core output fixtures; `tests/integration/test_openapi.py` checks export stability, response validation and generated-client compatibility. These paths are plans, not empty scaffolding to create now.

The HTTP paths, messages, statuses and auth scopes are defined in [API-CONTRACT](API-CONTRACT.md). Define reusable `Contract`, `HealthEvent`, `SceneEnvelope`, `Capabilities`, `ReplayReport`, `Error` and a faithfully derived `V3Snapshot`. OpenAPI must express finite bounds, nullability and closed objects. Strict parser duplicate/depth/nonfinite rejection and temporal invariants remain executable checks, because JSON Schema alone cannot enforce them. Parse raw replay bytes before any permissive framework JSON transformation.

## Export and validation sequence

1. Write protocol fixture tests first: invalid bool-as-number, duplicate fields, oversized frame, unknown fields and invalid contract must fail exactly as core.
2. Implement types and service using strict mode. Do not coerce strings into numbers or silently strip extra data.
3. Export canonical JSON using a pinned generator. Validate document with a pinned OpenAPI/JSON Schema validator selected and locked in P1.2; freeze its digest with the contract before client generation.
4. Generate TypeScript transport types first; compile the example client against the exported contract. For Swift Codable/Kotlin serialization, expose the same fixtures for the respective platform owner. C++ consumers initially use the JSON contract; no stable binary ABI claim.
5. Execute request/response conformance through a real installed loopback server from outside the checkout, including auth, errors, SSE gaps/expiry and shutdown. Mocking HTTP internals does not close this gate.
6. Diff exported contracts in PRs. A removed field, changed enum meaning, tightened externally accepted range or clock-semantic change requires an API major/versioned migration. Additive fields are not silently compatible with closed strict clients: negotiate a new schema revision and retain the old response shape.

OpenAPI docs assets must be bundled for offline use, not pulled from a CDN. Documentation pages are disabled or authenticated on enterprise deployments. API examples carry `SPEC ONLY` until tests run against actual built artifacts. No future endpoint is represented as live at the public PWA URL.

## Appliance ownership amendment within this proposed API

P1.2 must encode the appliance semantics from [API-CONTRACT](API-CONTRACT.md): POST attaches a viewer to an already booted pipeline; DELETE closes the viewer only; contract selection must match the configured pipeline. No API heartbeat, UI process or remote account sustains inference. Conformance includes zero-observer local operation and reboot/offline availability. This is a change to a SPEC ONLY API, not a migration of an existing deployed endpoint.
