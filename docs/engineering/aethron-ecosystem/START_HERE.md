# AETHRON ecosystem — Phase 0 blueprint

Status: **Phase 0 blueprint prepared; local commit blocked; Phase 1 NOT AUTHORIZED.** Prepared 2026-10-08. This area specifies an installable, cross-platform perception ecosystem for individuals, integrators and enterprises. Product work starts only when the owner explicitly says START. Nothing here certifies a vehicle, drone, sensor or safety function.

## Mandatory owner requirement — unattended, untethered operation

**The primary AETHRON product is a permanently installed, autonomous edge/embedded runtime, not a laptop- or phone-tethered camera demo.** After one-time provisioning, it must start automatically on host power-up and provide local perception, local API/status and recovery with no internet, cloud service, installer, terminal, external laptop/phone or user USB tether. Read [OWNER-NEXT-APPLIANCE-RUNTIME.md](OWNER-NEXT-APPLIANCE-RUNTIME.md) first, then the prioritized requirements in [NEXT.md](NEXT.md). Plan concrete OEM, sealed vehicle retrofit, onboard drone and smart-camera/NVR deployment models and explicit post-provision offline/reboot acceptance tests. Built-in or fixed-installed sensors, compute and power remain physically necessary. This is a required Phase 0 plan extension; **Phase 1 implementation still needs explicit owner approval**.

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
- All product pathways in this plan are **SPEC ONLY unless BASELINE explicitly identifies existing behavior**. Qualification is per software artifact, adapter, device tuple and operational domain.

## Phase 0 executable checks

From the repository root: `python3 scripts/check_ecosystem_plan.py --self-test`, then `python3 scripts/verify.py`. The dedicated preflight validates planning integrity only. It does not start a server, install a driver, touch hardware, publish packages or prove production behavior. See [handoff](HANDOFF.md) for actual local checks and limitations.

## Standalone runtime plan now integrated

Read [APPLIANCE-RUNTIME](APPLIANCE-RUNTIME.md) for supervisor ownership, boot/update/recovery and A01–A09 acceptance; [HOME-CAMERA-COMPATIBILITY](HOME-CAMERA-COMPATIBILITY.md) adds smart-camera/NVR deployment. Phase 1 now includes P1.7 boot-image/offline acceptance. These are SPEC ONLY; no auto-start service has been installed here.
