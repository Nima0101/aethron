# AETHRON ecosystem implementation plan

> Phase 1 was authorized and implemented. The original task checklists below are retained as the execution specification, not the current progress ledger. Use [PHASES](PHASES.json), [TEST-EVIDENCE](TEST-EVIDENCE.md) and [HANDOFF](HANDOFF.md) for executed acceptance and limits. P2–P5 remain future work; no subagents.

**Goal:** deliver installable, genuinely exercised local perception integrations, then expand to exact-device vehicle/UAS/nonvisible deployments with evidence-qualified claims.

**Architecture:** keep the frozen `aethron` core intact; build a separate `aethron_edge` package for source workers, trusted time/calibration, optional HTTP/SSE and installed clients. Native platform owners consume shared fixtures. New protocols and defensive control need separate approvals and evidence.

**Tech stack:** Python core/edge orchestration; pinned OpenCV existing inference; optional FastAPI/Pydantic/Uvicorn/HTTPX candidates; TypeScript consumer; later C++ vendor/camera worker and ROS 2 where justified. Swift/SwiftUI remains with its separate owner.

**Specification:** [architecture](ARCHITECTURE.md), [API](API-CONTRACT.md), [tests](TEST-EVIDENCE.md), [packaging](PACKAGING.md).

## Global constraints

Preserve v3 exactly: input 65536 bytes/depth 8; 5 unique sensor kinds; 64 detections; 32 tracks; age 100 ms; support skew 50 ms; prediction 200 ms; missed persistence 500 ms; track rotation 10 s; session reset 30 s. RGB eligible only in daylight. No support means UNKNOWN. Core T10 p95 ≤100 ms and peak ≤32 MiB remain unchanged. Prohibited identities/re-ID/pursuit/targeting/weapons never enter any extension. Through-obstruction stays coarse v2. API v1 wrappers never add fields to frozen v3 input.

No public push/merge/release/deployment/hardware actuation under this phase plan. Product coding is gated until owner START. No work outside assigned worktree or inside another agent's native iOS files/caches. Existing failed aircraft/latency/visual evidence is retained. Hardware absence does not block adapters and system-in-loop tests.

## Review focus

- Unknown camera capture clock must not become fresh evidence just because `read()` returned now — P1.3.
- Decoder stalls and a disconnected SSE stream must expire boxes with no next frame — P1.3/P1.4/P1.5.
- A strict client must not lose uncertainty, accept unknown enums, or attach a previous scene ID after reconnect — P1.2/P1.5.
- Installed packaging must work without checkout/PYTHONPATH/model auto-download and without native provider fallback — P1.1/P1.6.
- Changing source resolution/mount/clock must invalidate calibration and linkage, while remaining valid nonvisible sources survive RGB loss — P1.3/P2.1.

## Dependency and priority map

Critical Phase 1 path: P1.1 → P1.2 → P1.3 → P1.4 → P1.5 → P1.6 → P1.7. Each task ends with tests and one cohesive local commit. P2 model/data work can proceed independently of unavailable rigs once authorized, but its public claims wait for later gates. Effort estimates below are engineering ranges in focused person-days, not schedules or promises; review after each task. No cloud/GPU rental or hardware procurement is authorized by this plan.

### P1.1 — Installable edge package and existing-core consumer (1–2 days)

Owner: single Phase 1 implementer. Files: create `integrations/edge/pyproject.toml`, `integrations/edge/aethron_edge/__init__.py`, `__main__.py`, `cli.py`, `tests/integration/test_edge_install.py`, `examples/edge-replay.json`. Do not relocate existing core.

Consumes: installed `aethron==0.2.0`, `Session.step(data: bytes, now_ms: int)` and `Session.close()`. Produces `aethron-edge doctor/replay` and `replay_bytes(data: bytes) -> ReplayReport` interface finalized in P1.2. The initial replay command may call the existing bounded replay entry point until the strict transport report is introduced; no duplicate tracking implementation.

- [ ] Write `test_installed_replay_without_checkout`: fresh venv, install local wheels offline, run outside checkout with PYTHONPATH removed, require 24 fixture outputs and correct remaining sources.
- [ ] Run `python -m unittest discover -s tests/integration -p test_edge_install.py`; record failing missing-package/CLI result.
- [ ] Implement separate edge packaging and CLI, explicit model/provider reporting, local-only config. Preserve core Python floor; edge floor is 3.11.
- [ ] Build both wheels, run the test and existing `scripts/package_check.py`; doctor must not open hardware or download weights.
- [ ] Record distribution/import/entry-point behavior and commit exact task files.

### P1.2 — Strict typed contracts and exported OpenAPI (2–3 days)

Depends P1.1. Create `integrations/edge/aethron_edge/contracts.py`, `protocol.py`, `contracts/openapi/aethron-edge-v1.json`, `contracts/fixtures/v3/`, `tests/integration/test_edge_contract.py`, `test_openapi.py`. Finalize candidate dependency closure in `integrations/edge/requirements-server.lock` with exact versions/hashes/licenses; audit before installation/adoption.

Consumes raw v3 NDJSON and actual `Session` snapshots. Produces `ReplayReport`, `SceneEnvelope`, `HealthEvent`, `Capabilities`, `Error`, `Contract`, `Principal`, `SessionHandle`; export command `python -m aethron_edge export-openapi --out contracts/openapi/aethron-edge-v1.json`.

- [ ] Write table tests: 65537-byte line, depth 9, duplicate `at_ms`, boolean score, NaN, unknown field, replay >300 frames/30 s reject; accepted fixture bytes yield identical core results.
- [ ] Run `python -m unittest discover -s tests/integration -p 'test_*contract*.py'`; confirm failures before implementation.
- [ ] Implement closed types and raw-byte prevalidation; trusted now remains out-of-band. Capture real output fixtures, including UNKNOWN/watchdog and tentative/coasting states.
- [ ] Export/validate canonical OpenAPI, test all examples and error statuses; source-pin generator/validator. Run `test_openapi.py` plus core verification.
- [ ] Commit reviewed contract/types/locks/fixtures. Do not export unimplemented endpoints as a running service claim.

### P1.3 — Real source workers, time and calibration (4–7 days)

Depends P1.2. Create `integrations/edge/aethron_edge/sources/{base,file,uvc,rtsp}.py`, `timebase.py`, `calibration.py`, `pipeline.py`, `tests/integration/test_sources.py`, `test_clock_pipeline.py`, `tests/fixtures/edge/manifest.json`, `examples/edge-local.json`. Reuse existing `aethron/vision/yolox.py` via public adapter boundary; no model/threshold tuning.

Consumes `SourceConfig`; produces `Source.open -> SourceInfo`, `read(deadline_ns) -> FrameEnvelope|SourceFault`, `close`, `map_capture(frame: FrameEnvelope, now_ns: int) -> MappedFrame|SourceFault`, `build_v3(frame: MappedFrame, proposals: list, calibration: CalibrationRecord) -> bytes`. `MappedFrame` contains bounded image handle, mapped exposure/receive times and error; `CalibrationRecord` carries version/digest/validity/transform and residuals. Definitions stay in edge contracts, never injected into v3.

- [ ] Write fault-first source tests: disconnect/stall/reattach, oversized decoded dimensions, malformed encoded input, duplicate/out-of-order capture, unknown timestamp origin and camera reset. Assert bounded buffers, scene reset and no new fresh evidence.
- [ ] Write boundary tests at age 100/101 ms and skew 50/51 ms with uncertainty; remount/resolution invalidates calibration; stale inference cannot reset capture time.
- [ ] Run `python -m unittest discover -s tests/integration -p 'test_*sources*.py'` and `test_clock_pipeline.py`; record failures.
- [ ] Implement actual file, UVC and RTSP production acquisition workers with cancellation and explicit backend selection; isolate native decoder work. Use local RTSP fixture/virtual or fake capture backend for software tests while implementing real device code. Report delayed preview when exposure timing cannot be qualified.
- [ ] Run licensed pixels → actual pinned detector → registration → core. Assert ground truth absent from detector inputs, retain FP/FN including existing aircraft misses. Test queue 1 pending per source/inference, decoded-size and memory admission limits from architecture.
- [ ] Commit source/pipeline code and evidence. Mark exact physical SKUs untested until C-level evidence; no placeholder adapter called supported.

### P1.4 — Authenticated local service and SSE with watchdog (3–5 days)

Depends P1.3. Create `integrations/edge/aethron_edge/service/{app,auth,sessions,events}.py`, `tests/integration/test_edge_http.py`, `test_edge_sse.py`, `test_edge_security.py`. Wire actual `serve` CLI to the source pipeline.

Consumes named local source profiles and `SceneEnvelope`. Produces `open_session(profile, contract, principal) -> SessionHandle`, `snapshot(handle) -> SceneEnvelope`, `close_session(handle) -> None` and API paths in API-CONTRACT. Appliance supervisor owns trusted monotonic clock, configured pipelines and scheduling. HTTP session handles attach viewers only; their deletion/disconnection cannot stop inference.

- [ ] Write real-process tests requiring auth, scoped session ownership, no arbitrary source URI/command endpoint, exact 413/422/429 errors and sanitized malformed input. Slow subscriber cannot cause unbounded event storage.
- [ ] Write no-frame test: halt fake source, advance/wait trusted clock, watchdog/GET/SSE must report UNKNOWN; client reconnect gets gap/new snapshot rather than historical boxes.
- [ ] Run `python -m unittest discover -s tests/integration -p 'test_edge_*py'` and retain failing service tests.
- [ ] Implement loopback-only default, token file permissions/Host/Origin/CORS controls, latest-only event bus, worker shutdown, ≤4 sessions/≤8 subscribers. Explicit remote bind requires TLS deployment config.
- [ ] Execute subprocess client against installed server with a licensed recording and local RTSP fixture. Verify clean shutdown releases workers/ports, no camera/model download on health request.
- [ ] Commit actual service/security tests and logs. Implement the headless `run` supervisor entry and zero-viewer pipeline test now; P1.7 installs it into a boot image. Health does not certify perception.

### P1.5 — Usable developer clients and platform contract handoff (2–4 days)

Depends P1.4. Create `examples/clients/observe.py`, `examples/clients/typescript/`, `contracts/README.md`, `tests/integration/test_external_clients.py`, `docs/usage-edge.md`. Offer Swift/Kotlin fixture mapping as documentation; leave native iOS source/build to its owner.

Consumes OpenAPI/SSE and fixture corpus. Produces Python and TypeScript clients that display state, freshness, sources, uncertainty and delayed/replay labels; close sessions on exit. Browser client uses authenticated fetch streaming, not credential query strings.

- [ ] Write external-client assertions: current scene expires locally on disconnect/timeout/suspend; unknown enum fails closed; wrong auth/session rejected; no durable IDs/logged geometry.
- [ ] Run `python -m unittest discover -s tests/integration -p test_external_clients.py` and TypeScript type/contract test command defined in its package lock; preserve initial failures.
- [ ] Implement real installed clients, examples and exact install/run commands. Obtain source→service→client output from actual fixtures, not hand-authored green screenshots.
- [ ] Test offline assets/no CDN and conservative RTT/clock uncertainty behavior. No qualified transit bound means timestamped delayed observation, not current safety state.
- [ ] Commit clients/docs and provide fixture handoff via owner; do not contact or change other sessions.

### P1.6 — Cross-platform candidate, release evidence and inherited failure repair (3–6 days)

Depends P1.5. Create `scripts/edge_e2e.py`, `scripts/edge_package_check.py`, `scripts/edge_reproduce.py`, `tests/integration/test_artifact_contract.py`, `integrations/edge/container/Containerfile`, future dedicated edge CI. Modify existing workflow only after proving ownership/nonconflict. Repair existing visual reproduction only as authorized Phase 1 work, with a retained counterexample.

Consumes complete installed stack; produces source-bound evidence for A/B on actually executed platforms, multiarch build artifacts and explicit pending C/D matrix. Keep unsupported runners/providers marked pending, not fake green.

- [ ] Reproduce the inherited title-region visual mismatch against unchanged baseline; verify its cause before touching artifacts/generator. Preserve failure digests and corrected official logo.
- [ ] Write external wheel/container consumer and clean-clone rejection tests, plus no-private-payload logging assertions; run to expose missing artifact functionality.
- [ ] Implement actual packaging/CI and documented migration/update verification. Build Linux amd64/arm64 CPU images; distinguish emulated from native runs.
- [ ] Run all relevant static/type/unit/property/fuzz/frozen replay/metrics/security/license/SBOM gates; two clean builds; actual quickstart; README/client artifact reproduction. Retain failures. Native/GPU/HIL gaps do not disappear from support matrix.
- [ ] Update evidence/STATE/NEXT and commit packaging evidence. Continue to required P1.7 before declaring a Phase 1 candidate; no automatic push or Phase 2.

## Expansion phases — complete broad scope, separately authorized

| ID / priority | Files/modules to implement | Owner role / dependencies | Acceptance and cost concern |
|---|---|---|---|
| P2.1 high | `integrations/sensors/{lwir,nir,radar,depth}/`, packet schemas/calibration fixtures | sensor implementer; P1.3 | Real licensed packet/pixel replay plus physical-ready drivers; malformed/skew/loss; no hardware needed to write code. Thermal SDK/optics cost and raw-buffer memory measured |
| P2.2 high | `evaluation/splits/`, `evaluation/models/`, `evaluation/tracking/`, versioned model cards | evaluator; data rights + P2.1 | Freeze held-out protocol, train compact thermal/small-UAV candidates, compare baselines, calibration/FP/FN/HOTA. GPU training/storage budget approved separately |
| P2.3 high | provider workers, `benchmarks/edge/`, fuzz harnesses | runtime implementer; P2.2 | CPU/Core ML/TensorRT/NPU equivalence, cold/warm end-to-end timing and RSS/power; no silent fallback |
| P3.1 high | `integrations/ros2/`, `integrations/mavlink/`, SITL fixtures | robotics implementer; P1/P2 | Image/CameraInfo/clock/QoS and read-only telemetry E2E, pinned PX4/ArduPilot simulator matrices, no command output |
| P3.2 medium | optional DJI/Parrot/vendor plugin packages and license manifests | vendor adapter implementer; exact SDK rights | Actual SDK build/stream handling, mocks plus documented unavailable SKUs, activation/offline limits |
| P3.3 high | `sdks/typescript/`, Android modules, desktop launchers, native contract fixtures | respective platform owners; P1.5 | Real install/use/uninstall/update and permission/lifecycle tests; Swift changes only by native owner |
| P3.4 medium | authorized vehicle telemetry adapters, fleet config/update service | vehicle integrator; P1 + authorization | UVC/CSI/GMSL/IP recipes across ICE/EV/fleet/motorcycle; no OEM camera assumption; managed aggregate health |
| P4.1 high | `qualification/rigs/`, calibration/clock/environment records | device owner/test team; P2/P3 | C-level exact SKU evidence; power/thermal/clock instrumentation and mount costs budgeted per rig |
| P4.2 high | `qualification/domains/`, hazard/field/privacy/security reports | independent evaluator; P4.1 | D-level held-out domain evidence, sample-size/confidence analysis, independent review and applicable certification |
| P5 optional | separately reviewed bounded defensive-controller interfaces | owner + platform safety integrator; P4.2 | New authorization, system safety case/HIL/manual override; no pursuit/targeting/weapons ever |

## Supported versus not yet supported

Existing support is precisely [BASELINE](BASELINE.md): a local research runtime and its demonstrated paths. P1 implementation and evidence are recorded in PHASES and HANDOFF; the original unchecked planning checklist is retained below. P2–P5 remain unimplemented in this lane. Intended platform availability is not support. Broader vehicle/drone/sensor scope is preserved in these tasks, with shared contracts and recipes; phased implementation changes sequencing, not the owner's goal. Do not declare the entire ecosystem finished when only P1 is delivered.

## P1.7 — Mandatory standalone appliance boot and offline acceptance (4–7 days)

Depends P1.1–P1.6; designed from P1.1 and supervisor implementation in P1.4. Owner: single Phase 1 implementer. This is required Phase 1 work, not deferred optional polish. Specification: [owner requirement](OWNER-NEXT-APPLIANCE-RUNTIME.md), [APPLIANCE-RUNTIME](APPLIANCE-RUNTIME.md), A01–A09. Product remains observation/assistance without actuation.

Create `packaging/appliance/systemd/aethron.service`, `packaging/appliance/install.py`, `packaging/appliance/image/`, `integrations/edge/aethron_edge/runtime/{supervisor,health,provisioning,updates}.py`, `scripts/appliance_boot_e2e.py`, `tests/integration/test_appliance_lifecycle.py`, `tests/integration/test_appliance_updates.py`, `docs/usage-appliance.md` and class-specific one-page operator guides. Extend P1.4 supervisor rather than duplicate pipeline code.

Consumes signed local runtime/model/plugin/config manifests and Source ABI. Produces `ApplianceSupervisor.boot(config: ApplianceConfig) -> RuntimeStatus`, `tick(now_ns: int) -> RuntimeStatus`, `shutdown(reason: ShutdownReason) -> None`, `attach_observer(profile: str, principal: Principal) -> SessionHandle`; update interface `stage_update(bundle: Path) -> VerifiedCandidate`, `activate(candidate: VerifiedCandidate) -> ActivationResult`, `recover() -> RuntimeStatus`. Config/keys may persist; no live tracks or raw imagery persist. Normal startup uses `aethron-edge run --config appliance.json` launched by the OS, not by a user terminal.

- [ ] Write failing lifecycle tests: zero viewers, lost WAN/cloud/phone/provisioner, cold boot, disk-full, sensor/zero-light loss, stale frames, provider failure, worker hang and restart budget 5/60 s. Assert local pipeline/indicator state is independent, UNKNOWN expires evidence, and restart never restores IDs.
- [ ] Write failing update tests: bad signature/hash, missing model, interrupted inactive-slot write, incompatible config, revoked rollback, factory reset. Require offline last-known-good compatible recovery or explicit fault, never automatic download/activation dependency.
- [ ] Run `python -m unittest discover -s tests/integration -p 'test_appliance_*.py'`; retain expected failures.
- [ ] Implement dedicated-account service installer, enabled boot unit, bounded restart/logging, restricted device permissions, local notifier/API and transactional update/provisioning recovery. Never install it on the development Mac as an incidental test.
- [ ] Build signed local candidate images/manifests with test-only signing keys clearly separated from future release keys. Boot a pinned Linux VM through its real service manager, close/remove provisioning channel, disable WAN, reboot without login, disconnect all observers and verify local outputs from a recorded/virtual source. Execute `python scripts/appliance_boot_e2e.py --image build/appliance/test-image` against the actual produced image; process-only unit startup does not pass A01/A02.
- [ ] Run one-hour software soak with latency/drop/RSS/log-growth data and injected worker faults; preserve any failure. Label simulation; no physical wattage/temperature/brownout/accuracy claim. Document pending exact hardware gates separately.
- [ ] Exercise OEM-authorized deployment recipe where access exists, fixed vehicle retrofit, onboard drone and home NVR/hub normal-user guides; distinguish documented software recipes from measured SKU support. Phone camera sessions obey OS restrictions; phone remains optional for appliance modes.
- [ ] Commit source-bound image/service/consumer evidence and report A01–A09 status. Stop after the complete Phase 1 candidate for owner review; no automatic Phase 2/publication.

P3.4 additionally implements OEM-native and production appliance provisioning/manufacturing integration; P4.1 expands A03/A04/A06/A09 to actual power/ignition/payload/PoE, nonvisible optics and environment measurements. Lack of hardware does not block P1.7's real boot-VM/software implementation.
