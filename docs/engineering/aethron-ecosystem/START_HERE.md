# AETHRON ecosystem — implementation entry point

**Phase 1 P1.1–P1.7 is complete as a locally tested software candidate.** The [acceptance record](evidence/phase1/acceptance.json) binds the reviewed source, installed artifacts and completed one-hour Linux boot test. The [recorded approval](PHASE1-START-AUTHORIZATION.md) supersedes the historical Phase 0 stop text. Phase 0 committed at `58a2a9d`; the approved public-main merge is `8d0da0e`; approval is `1445f18`. The later [owner autonomy directive](LATEST-OWNER-AUTONOMY.md) authorizes continuous software work through P2–P5 and routine publication after legitimate release gates. P2.1 sensor implementation is now underway; hardware and actuation remain outside that authorization.

Start with [current state](STATE.md), [next executable task](NEXT.md), [machine status](PHASES.json) and [handoff](HANDOFF.md). For actual commands use [edge installation](../../usage-edge.md) and [installed appliance](../../usage-appliance.md). Read the [execution ledger](EXECUTION.md) for regressions and retained failures. Project-owned software is GPL-3.0-only, with separately negotiated commercial licensing; third-party terms remain distinct.

## Normal operation

The consumer product is an independently installed appliance: provision once, then power on into local supervised processing and status. No routine user terminal, laptop/phone tether, provisioning USB, WAN, Supabase, Coolify or licensing heartbeat is required. The Linux image and systemd service implement this software lifecycle. Permanent compute, sensors, protected power and approved mounting remain necessary. Native iOS belongs to its separate owner and is untouched.

The boot test uses synthetic multimodal proposals. File/RTSP pixels and virtual UVC exercise actual source boundaries separately. Generic OpenCV capture has unqualified exposure time and cannot establish current safety evidence. Physical zero-visible sensing, OEM camera access, electrical/thermal behavior and safety certification remain unqualified. Local status is informational, never a SAFE assertion.

## Read in order

1. [State and baseline](STATE.md), [checked evidence](BASELINE.md), [next actions](NEXT.md), [machine-readable phases](PHASES.json).
2. [Research decisions](RESEARCH.md), [primary sources](SOURCES.md), [source provenance](provenance.json), [version selections](versions.json).
3. [Architecture](ARCHITECTURE.md), [API contract](API-CONTRACT.md), [OpenAPI plan](OPENAPI-PLAN.md), [packaging](PACKAGING.md).
4. [Vehicle decision tree and recipes](VEHICLE-COMPATIBILITY.md), [Mazda example](MAZDA-3-2019.md), [drone pathways](DRONE-COMPATIBILITY.md), [night sensing](SENSOR-NIGHT.md).
5. [Development workflow](WORKFLOW.md), [CI and release](CI-RELEASE.md), [test evidence and qualification](TEST-EVIDENCE.md), [threat model](THREAT-MODEL.md), [conditional standards](ASSURANCE.md).
6. [Implementation backlog](IMPLEMENTATION-BACKLOG.md), [Phase 1 execution prompt](PHASE1-EXECUTION-PROMPT.md), [handoff](HANDOFF.md).

## Authority and scope

The [owner amendment](../../safety/amendment-v3.md), [frozen protocol](../../architecture/protocol-v3.md), [frozen verification matrix](../../verification/matrix-v3.md) and root AGENTS govern. This blueprint adds transport/installation plans; it does not amend any frozen threshold. Existing governance and data/model hashes stay byte-identical. A future protocol change needs a separate versioned amendment and new preregistered evaluation.

Baseline: `59fda946771d4ac8c9d1b52eeb3d948215325e4c`, branch `feat/aethron-vehicle-uav-preparation-20261008`. Existing package `aethron` 0.2.0 is a research runtime; the [camera PWA](https://nima0101.github.io/aethron/) is a separate browser preview. Neither proves global qualification. The corrected AETHRON logo remains unchanged. The separately owned native Swift/SwiftUI implementation is outside this worktree's assignment; this area offers wire contracts and fixture requirements for later integration.

## Decisions to carry forward

- Retain the bounded Python core and existing CLI. Add a separately packaged edge integration layer; the core's no-network static policy remains enforceable.
- Implement real UVC/file/RTSP drivers and local service clients before claiming end-to-end integrations. Hardware absence permits adapter coding, recorded input and system-in-loop testing.
- Start with local HTTP plus SSE, a strict OpenAPI 3.1.1 contract and explicit plugin allowlist. Add ROS 2 at the robotics boundary; defer gRPC until measured copy/throughput requirements justify it.
- RGB is daylight-only in v3. True zero-visible operation needs valid LWIR/NIR/radar/depth evidence, suitable optics, clock/calibration provenance and representative evaluation.
- Factory cameras are not universally accessible. OBD-II/CAN and phone projection do not grant camera access. Keep generic retrofit recipes useful across powertrains and body classes.
- Use PHASES and the Phase 1 handoff for executed capabilities. Research documents retain the broader roadmap; exact hardware and field qualification remain separate.

## Verification and phase boundary

Run `python scripts/check_ecosystem_plan.py --self-test` and `python scripts/verify.py` for planning/governance integrity. Actual package, source, installed HTTP/SSE and boot-image checks are documented in [TEST-EVIDENCE](TEST-EVIDENCE.md) and [CI-RELEASE](CI-RELEASE.md). Green planning checks are not product qualification.

[APPLIANCE-RUNTIME](APPLIANCE-RUNTIME.md) specifies A01–A09; [HOME-CAMERA-COMPATIBILITY](HOME-CAMERA-COMPATIBILITY.md) covers smart-camera/NVR paths. Original Phase 0 wording and negative evidence remain in Git history and the historical snapshot. Automatic software advancement now follows the later owner directive; no release gate or physical qualification is waived. The [Phase 1 completion snapshot](evidence/phase1/phase1-completion-snapshot.json) retains the earlier stop state.

P2/P3 implementation: [sensor packet/replay contracts and pinned sources](P2-SENSOR-ADAPTERS.md), [installed ROS sidecar](../../../integrations/edge/ros2/README.md), and [executed ROS software evidence](evidence/phase2/ros2.json). Registration, nonvisible semantic providers and physical qualification remain pending.
