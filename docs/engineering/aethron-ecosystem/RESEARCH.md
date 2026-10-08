# Research synthesis and decisions — 2026-10-08

This is original Phase 0 analysis of the checked repository and current primary sources, not a claim that researched integrations exist. Source IDs resolve to [SOURCES](SOURCES.md), which records versions, retrieval dates and limitations. [BASELINE](BASELINE.md) separates inherited evidence, fresh executions and actual failures.

## R1 — A practical installation needs a boundary outside the core

The existing wheel/import/CLI is real software. However users still need OS permissions, source negotiation, trustworthy timestamps, calibration, provider/model installation, supervision, useful client output and fault recovery. Reusing `scripts/live_video.py` as a prototype does not make a stable SDK. A separately distributed edge layer preserves the frozen core's no-network policy while allowing a usable local service and independently installed clients.

Alternatives considered: rewrite everything in a native language; make ROS 2 mandatory; extend Python with a separately packaged integration layer. Select the third for Phase 1 because it reuses verified semantics and permits C++/Rust workers later where an SDK or measured performance warrants them. We do not cap the long-term platform scope at Python.

## R2 — Vehicle access is an authorization and hardware matrix

Projection frameworks govern UI distribution, not access to arbitrary vehicle video. Current Apple documentation now includes parked video [S01](SOURCES.md#s01), so a blanket “CarPlay never supports video” statement would be stale. That change does not establish a camera entitlement. Android Auto and AAOS differ architecturally [S02](SOURCES.md#s02). OBD diagnostic scope [S04](SOURCES.md#s04) does not deliver pixels. Factory serializers, gateways and vendor software require exact integration rights and electrical evidence.

Choose external authorized camera + portable compute as a credible generic route across older ICE cars, modern hybrid/EVs, fleets, buses and motorcycles where mounting/power permit. UVC is simpler to prototype; CSI offers embedded integration; GMSL offers automotive cabling but requires matched hardware/drivers [S06](SOURCES.md#s06). IP streaming can simplify placement but creates latency/authentication and network-partition risks. None means every product using that connector works. [Vehicle recipes](VEHICLE-COMPATIBILITY.md) turn these distinctions into installation steps.

## R3 — Drone telemetry and camera pixels are separate channels

PX4 has a concrete versioned ROS 2 path; Agent major compatibility is a real integration constraint, not a cosmetic pin [S10](SOURCES.md#s10), [S11](SOURCES.md#s11). ArduPilot exposes companion telemetry [S12](SOURCES.md#s12); MAVLink camera protocol describes streaming endpoints but does not solve synchronized image metadata [S13](SOURCES.md#s13). Build a camera source and clock mapper independently of vehicle command APIs.

DJI V5 product/Android release metadata is discoverable, but firmware/controller/payload rights must still be selected and proven [S15](SOURCES.md#s15)–[S17](SOURCES.md#s17). Parrot Olympe provides a documented Linux frame API and simulator pathway, with a meaningful x86_64 prebuilt limitation [S18](SOURCES.md#s18). A proprietary unsupported radio feed stays unsupported; external payload/authorized network streams remain options. Companion execution avoids a mandatory radio/cloud latency leg. Ground station remains useful for delayed observation when freshness cannot close.

## R4 — Zero-visible performance requires physical evidence and explicit abstention

Thermal sensing uses emitted radiation; NIR/SWIR reflectance paths depend on appropriate photons, and active depth/radar have their own interference/material limitations [S22](SOURCES.md#s22)–[S24](SOURCES.md#s24). Calibration/time uncertainty dominates safe fusion: a fast detector cannot repair wrong extrinsics or silently aged network frames. V3's single registered image plane is useful but not a generic metric 3D autonomy stack.

Select staged nonvisible adapters and recorded/simulator evidence before physical qualification. Maintain valid nonvisible tracks during RGB loss. Invalid registration suppresses localization; all-support loss means UNKNOWN. Treat solar loading, contrast crossover, window material, rain/fog and emitter failure as first-class test partitions, not rare corner cases.

## R5 — Models and tracking need comparative evidence

| Candidate | Why evaluate | Risk / adoption condition |
|---|---|---|
| Existing classical contrast detector | Transparent no-dependency baseline, fixed original pixels | 20 FN/721 FP on AOT; no semantic UAV discrimination; retain as negative baseline |
| Existing pinned YOLOX | Apache source, real model/provider path and positive still smoke | 20 aircraft misses; RGB-only; no thermal/UAV accuracy; keep model hash and original thresholds |
| New compact thermal detector trained on licensed data | Direct nonvisible pedestrian/vehicle/small-UAV evidence | Freeze data splits and weights; prove modality/class support, imbalance, unseen-weather FN and calibration |
| Larger detector/transformer exported to ONNX | Potential recall gain for small/occluded objects | Measure compute/memory and resize/tiling losses; no choice based only on vendor FPS |
| Frozen geometric Kalman + assignment | Existing bounded temporal evidence and uncertainty rules | Wrong motion model/fast crossing/rotation can misassociate; compare identical detections against simpler baseline |
| Greedy IoU | Fast, auditable lower-complexity comparator | Small/fast objects lose overlap; current frozen fast-UAV ID-switch result exposes this |
| ByteTrack-style low-score association | Can recover weak observations [S27](SOURCES.md#s27) | Clutter can extend false tracks; frozen thresholds cannot be changed under v3; no appearance re-ID |
| FLIT-inspired L2 + IoU | Small-object positional distance can supplement overlap [S51](SOURCES.md#s51) | Paper excerpt/Visage PoC motivate testing; do not copy a qualitative performance claim |

OpenCV's Kalman primitive is an implementation alternative [S57](SOURCES.md#s57), not justification for replacing the current deterministic math without equivalence tests. HOTA/TrackEval adds a recognized sequence-level metric [S28](SOURCES.md#s28); current T09 metrics remain frozen. Add new benchmark reports rather than rewriting historical metrics.

Visage's April 2026 PoC discusses thermal imagery, geometry-based temporal association, camera motion and weaknesses in solar loading/small images [S19](SOURCES.md#s19). Its cited SUAVE-600 v3 could not be independently located with clear licensing; keep it an unresolved lead. The original Anti-UAV challenge and repository were inspected [S52](SOURCES.md#s52), [S53](SOURCES.md#s53): repository MIT terms do not automatically settle separately hosted image rights. Related Visage edge/safety/autonomy pages were attempted via web and direct requests but returned errors/403 [S48](SOURCES.md#s48)–[S50](SOURCES.md#s50); no claim is drawn from their unseen contents.

## R6 — Runtime choices must fit the complete deadline

A source-to-visible-output budget includes exposure, transfer, decode, preprocess, inference, registration/fusion and delivery. The current core-only 100 ms p95 benchmark is not that budget. Proposed feasibility allocation: capture/transfer 15 ms, decode/preprocess 10 ms, inference 40 ms, core 15 ms, delivery 10 ms, margin 10 ms. These are design targets whose sum is 100 ms, not measured guarantees; the frozen gate still rejects any stale frame. Camera rate, long exposure, cold-start compilation and network buffering may invalidate the allocation before the tracker runs.

Measure cold and steady state separately; CPU, Core ML, TensorRT/GPU, OpenVINO/NPU candidates require exact provider/driver/operator coverage and numerical checks [S25](SOURCES.md#s25). Raspberry Pi-class CPU-only semantic inference may miss budget; Linux mini-PC/GPU alternatives stay in scope. Quantization can lose small-object recall; benchmark held-out results and memory, not just throughput. Scheduling/throttling on general-purpose operating systems cannot establish a hard real-time guarantee.

## R7 — API-first does not require every transport on day one

OpenAPI with a small HTTP surface plus SSE serves Python/TypeScript/Swift/Kotlin and enterprise clients [S29](SOURCES.md#s29), [S30](SOURCES.md#s30). Keep raw byte validation, client expiry and bounded ownership explicit. ROS 2 is useful at the sensor/companion edge. Add gRPC only for measured IPC throughput or generated native-client needs; avoid duplicate schemas with inconsistent failure semantics. Offline wheelhouse/container installation and explicit model fetch enable sites with no cloud accounts [S31](SOURCES.md#s31).

## R8 — Qualification is a ladder, not a green badge

Installation, software E2E, hardware SKU compatibility, intended-domain field validation and certification are independent records. Automotive functional safety/SOTIF/cybersecurity and vehicle update regulations may become applicable through the integrator's intended use [S34](SOURCES.md#s34)–[S37](SOURCES.md#s37). Aviation/airspace and privacy rules depend on geography/operation [S38](SOURCES.md#s38)–[S42](SOURCES.md#s42). No current evidence supports a certified driving/rescue guarantee. [ASSURANCE](ASSURANCE.md) specifies work products and decision owners without inventing an approved state.

## R9 — Owner-required permanent runtime changes the delivery priority

The [owner appliance requirement](OWNER-NEXT-APPLIANCE-RUNTIME.md) makes one-time provisioning and unattended offline startup the primary user experience. API-first remains useful for integrations but cannot imply that an API connection or phone owns perception. Prefer documented OEM-native deployment; otherwise choose a permanently installed vehicle/drone/home edge appliance. Bench laptops and CLI remain developer tools. Linux/systemd boot is the first testable service-manager target; runtime/service and isolation references are pinned to v255 documentation [S63](SOURCES.md#s63), [S64](SOURCES.md#s64), with actual distribution version/digest resolved before implementation.

Mobile platform restrictions are material: Apple documents capture interruption when backgrounded [S61](SOURCES.md#s61); Android documents camera foreground-service permission/start/boot restrictions [S62](SOURCES.md#s62). Do not evade them or reinterpret a background execution thread as permission for unattended background capture. A native mobile client is optional to permanently integrated modes. [APPLIANCE-RUNTIME](APPLIANCE-RUNTIME.md) and [home recipes](HOME-CAMERA-COMPATIBILITY.md) make standalone boot/update/local status concrete without implementing a feature in Phase 0.
