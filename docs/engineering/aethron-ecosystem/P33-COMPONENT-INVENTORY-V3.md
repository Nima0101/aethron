# P3.3 / P12 source and review inventory

Snapshot baseline: `e4110809291cb8a5d9c449b91fc8c2a247e7bd9e`, plus the
validation-probe correction recorded in this slice. This is an inventory of the
owned source surface and review evidence, not a lane-completion declaration.
The [JSON snapshot](evidence/phase3/p33-component-inventory-v3.json) records every
tracked file under both client packages, plus the owned compatibility entry,
packed-consumer driver, controlled fixture/tests and client workflow. Generated
build output and dependencies are excluded; dependency locks are included.
Each exact hash match means only that retained evidence identifies those bytes.
Older V2 evidence is not relabeled V3, and a match does not prove correctness.

The chronological decisions, corrections and negative results remain in
[P33-REVIEW-V3](P33-REVIEW-V3.md). Later slices supersede earlier cursor statements.
The following grouped index makes the substantial executable surfaces explicit.
Paths in the first column are relative to their indicated package unless qualified.

| Component and entry points | Current decision and review reference | Remaining limitation |
| --- | --- | --- |
| SDK contract declarations: `generate-contract.mjs`, `src/types.ts`, `src/scene.schema.json`; `scripts/edge_generate_types.py` compatibility launcher | MIGRATE completed to Node-owned generation; KEEP the closed selector subset and AJV metaschema shape checks. `p33-generator-selectors-v1.json`, `p33-generator-structure-v1.json` | This is a subset generator, not arbitrary OpenAPI support. Producer owns contract changes. |
| SDK standalone admission: `generate-validators.mjs`, `src/validators.d.cts` | MIGRATE runtime compilation to build-time AJV completed; V3 independent negative admission tests retained. `p33-generation-review-v3.json`, `p33-build-lifecycle-v1.json` | Shared-AJV parity is not independent correctness. |
| SDK build: `build.mjs`, package/TypeScript configuration | KEEP sequential Node compiler lifecycle; failure removes generated output. `p33-build-lifecycle-v1.json` | One build per package directory; no hostile workspace isolation. |
| SDK aggregate observation: `src/client.ts` / `Observation` | KEEP private aggregate projection and local clock; FIX clock exceptions, cloning/reentrant revocation. `p33-observation-review-v3.json`, `p33-reentrant-admission-v3.json` | No transport freshness, secure deletion, anonymity or hard scheduler bound. |
| SDK byte/session ingress: `src/wire.ts`, `src/session.ts` | KEEP bounded native byte buffers and strict lexical admission. `p33-session-boundary-v1.json`, numeric/session review slices | Complete SSE-event cap and producer JSON-only cap still require producer reconciliation. |
| SDK session/source/render lifecycle: `src/client.ts` / source and observer functions | KEEP fetch/AbortSignal composition; setup, abort/reentrancy and callback corrections retained. `p33-observer-setup-v1.json`, `p33-observer-revocation-v1.json`, `p33-source-composition-v1.json`, `p33-render-publication-v1.json` | Cancellation requests do not guarantee remote deletion or cooperative source cleanup. |
| SDK endpoint and transport oracles: `audit-redirect.mjs`, `audit-cancellation.mjs`, `audit-session-boundary.mjs` | KEEP actual host fetch/stream primitives and bounded child checks. `p33-transport-install-review-v1.json`, `p33-cancellation-oracle-v1.json`, `p33-session-boundary-v1.json` | Synthetic controls, not deployment qualification. |
| SDK validation comparison: `audit-validation.mjs` | KEEP Node/AJV; FIX missing session workload and add correctness-only mode. `validation-probe-adr.json`, `p33-validation-probe-review-v1.json` | Historical timings remain historical; no comparative compiler benchmark. |
| SDK observation comparison: `audit-observation.mjs` | Historical private-field/closure probe retained; projection review covers runtime correctness | Next auxiliary evidence-producer review: check its report provenance and scope against current projection. No fresh completion inferred from a matching old hash. |
| SDK archive and offline install: `installed-runtime.mjs`, `offline-consumer.mjs`, package tests | KEEP pinned npm archive/lock boundary with strict manifest admission. `p33-transport-install-review-v1.json` | Cross-version upgrade and customer distribution/signing are unqualified. |
| Packed service driver: `scripts/edge_node_e2e.py`, `tests/integration/test_node_consumer_smoke.py` | KEEP Python driver plus actual installed Node consumer; report admission corrected. `p33-service-harness-review-v1.json` | Actual production-service run has separate dependency and execution evidence. |
| Controlled loopback fixture/tests | KEEP Python stdlib; FIX optimization-sensitive gates. `p33-loopback-evidence-review-v1.json` | Controlled handlers do not establish production-server acceptance. |
| P12 presenter/panel: `src/presenter.ts`, `src/panel.ts` | KEEP TypeScript/native plain-text DOM; clear on invalid source and reentrant revocation. `p12-display-build-review-v1.json` | Direct object cloning is not a pre-allocation byte bound; current state remains UNKNOWN. |
| P12 lifecycle: `src/lifecycle.ts` | KEEP explicit host visibility/page lifecycle. `p12-lifecycle-review-v1.json` | Event delivery and native browser behavior need target qualification. |
| P12 connection/client: `src/connection.ts`, `src/client.ts` | KEEP deterministic connection and containing-client state; human reconnect after cancellation. `p12-connection-review-v1.json`, `p12-client-review-v1.json` | UI enablement is not authorization; host/service enforce access. |
| P12 builds/entry point: `build.mjs`, `build-browser.mjs`, `src/browser.ts` | KEEP direct compiler plus esbuild; FIX binding provenance to consumed source bytes. `p12-display-build-review-v1.json`, `p12-browser-provenance-review-v1.json` | A generated manifest is not a signed release or customer installation. |
| P12 contextual help: `help-inventory.mjs`, `src/action-help.ts` and literal guidance | KEEP TypeScript AST extraction/native DOM; FIX coverage claims and mount-tree ID collision handling. `p12-help-inventory-review-v1.json`, `p12-action-binding-review-v1.json` | Ten states/four buttons only; no complete product help or assistive-technology qualification. |
| Client hosted workflow | KEEP focused package, type, artifact, harness and negative-control checks; last fixture correction adds normal/optimized Python runs | Workflow existence and queued jobs are not PASS evidence. |

## Unfinished owned software and external gates

- P3.3 Android/JVM and desktop client launch/upgrade contribution: deployment
  requirements and technology selection remain open; no native implementation
  is claimed. P11 operating-system install/provision belongs to the fleet lane.
- P12 full scene/map/mission/replay client and integrated offline synthetic demo
  remain unfinished; the shipped example is a reusable read-only observation UI.
- P19.7 search, onboarding, role/route/error coverage, manuals and version-matched
  integrated help remain unfinished. Current state/action inventories cover only
  the actual example component and explicitly list missing product coverage.
- Native browser/accessibility runs, signed installed distribution and independent
  non-developer acceptance need actual evidence. They cannot be inferred from Node
  DOM tests. Final integrated P19 acceptance also depends on upstream gates.
- The producer SSE boundary request remains in the lane runtime handoff; the
  consuming lane must not change the producer or silently increase frozen limits.
- Native iOS, weapon integration, target designation and actuation are outside this
  lane. No sensor fusion or tactical deployment capability follows from these clients.

Next earliest review item is the retained observation-comparison evidence producer.
The inventory itself does not authorize forward feature expansion or create an
`audit_complete` marker. Insufficient information for tactical deployment.
