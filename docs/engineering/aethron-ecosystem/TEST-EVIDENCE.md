# Test evidence and qualification matrix

## Four claims that must stay separate

| Level | Acceptance | Evidence and exclusions |
|---|---|---|
| A — installable software | Build and install exact artifact on each declared OS/arch/Python; external import/CLI consumer executes replay offline | Artifact hashes, dependency closure, clean environment log; no camera/field claim |
| B — working adapter and software E2E | Actual driver implementation accepts licensed recording/simulator/device data, processes through real model/core, emits contract-valid output consumed by installed client; failure handling exercised | Input/model/code hashes, clocks, FP/FN and output/visuals; fake device proves driver semantics only |
| C — hardware compatibility | Exact camera/compute/SDK/OS/firmware/connector/calibration tuple captures and processes on real rig with measured clocks, power, thermal and reconnect behavior | SKU test report and operational bounds; no general vehicle/model-family or certified safety claim |
| D — real-world safety/assurance | Representative held-out intended-domain trials meet preregistered requirements, hazard/cyber/privacy reviews complete; external certification if applicable | Statistical intervals, coverage, residual hazards, independent reviewer and applicable authority records; unavailable evidence blocks claim |

Phase 0 preflight is **planning integrity**, outside A–D. Synthetic semantic tests cannot jump from B to D. Hardware access is not required to implement B's adapter code and simulator harness.

## Traceable test requirements

| ID / backlog | Test and acceptance | Existing gate / evidence lane |
|---|---|---|
| E01 / P1.1 | Existing v3 bytes round-trip; invalid duplicate, bool numeric, nonfinite, unknown fields rejected; literal bounds retained | T01; core + contracts |
| E02 / P1.3 | RGB blackout with valid thermal/radar/depth preserves current provenance/box; all loss UNKNOWN; no phantom births | T02/T04; semantic fixtures |
| E03 / P1.3 | Capture clock wrap/drift/reset; 100 ms age and 50 ms support skew enforced including uncertainty | T06; source fake + replay |
| E04 / P1.3 | Real codec/file path, malformed/truncated frame, huge dimensions, disconnect, reattach, unreadable timestamp | Decoder process and bounded memory; no stale frame re-dating |
| E05 / P1.4 | Auth/Host/Origin/session isolation; invalid error payload sanitized; 413/422/429; no arbitrary URL/command endpoint | Security integration |
| E06 / P1.4–P1.5 | Stop source without a new frame; watchdog and client expiry withdraw current boxes; reconnect gap then new snapshot | T03/T08; installed SSE client |
| E07 / P1.3–P1.4 | Queue flood cannot grow frame/event buffers; slow SSE subscriber disconnected; resource exhaustion yields UNKNOWN | Bound-focused stress/RSS |
| E08 / P1.5–P1.6 | Install wheel in fresh environment outside source; actual CLI/server/sample-client path on target OS | T12; A and B |
| E09 / P2.2 | Crossing objects, camera pan/rotation, ambiguity, reentry after expiry, no re-ID fields/embeddings/history | T03/T05/T07, retained negatives |
| E10 / P2.2 | Dataset partition/model freeze before held-out inference; full-frame pixel path; independent evaluator | T09/T13, current AOT failure retained |
| E11 / P2.3 | ≥2,000 randomized cases and ≥60 s each required temporal/legacy fuzz; zero unexpected exceptions | T11, source-bound reports |
| E12 / P2.3 | Frozen 100-frame/32-object core p95 ≤100 ms, traced peak ≤32 MiB; report p50/p95/max and all failures | T10; not whole-system FPS |
| E13 / P3 | Linux/macOS/Windows x86/ARM install/client lanes; exact unsupported dependency availability explicit | T12/T14; executed versus pending |
| E14 / P4 | Physical true-zero-visible, sensor loss, weather, power/thermal, clocks/calibration | T15; C then D |
| E15 / P5 | Qualified bounded defensive-controller failure tests and independent review if ever authorized | Separate future control gate, no Phase 1 actuation |
| E16 / P1.6 | Byte-identical README visual reproduction; diagnose current mismatch without overwriting historical evidence | T12; title-region counterexample retained, derived visuals repaired and reproduced |

## Harness requirements

A fake source implements the real Source ABI, deterministic scheduler, controllable timestamps, decoder faults, calibration expiry and queue stalls. File replay drives the production decode/inference boundary using licensed pixels, not detections copied from ground truth. A local RTSP fixture server streams pinned video without a physical camera; a virtual UVC source or capture backend contract harness exercises negotiation/close/reopen. Label these system-in-loop, not physical hardware.

A recorded modality proposal fixture is useful for time/fusion semantics but cannot qualify the missing physical decoder/model. Cover both: strict proposal replay for exhaustive state tests and real pixel/sensor-packet replay for each actual driver. ROS bags and MAVLink logs must have stripped serial/location/person histories or approved licensed evaluation provenance. No arbitrary live recording API is added under the guise of tests.

## Evaluation design

Preregister class definitions (person, cyclist, vehicle, UAV, animal, obstacle, equipment, hot/cold, fire-like, smoke), operational domain and sample strata. Do not promise every class from a generic COCO model. Treat fire-like/smoke as cues, not diagnosis. Split by site/session/rig/time and document training leakage risks. Freeze hashes for datasets, splits, labels, models, preprocessing, calibration and evaluator. Record class/condition FN, FP, localization, switches, fragmentation, observed recall, abstention and confidence calibration; predictions scored separately. Add a pinned HOTA evaluator for new studies, keeping frozen v3 metrics intact.

For proposed field accuracy thresholds, the owner/system assessor must preregister numbers from intended risk and sample-size analysis before collecting/evaluating the held-out set. This is a concrete gating work product, not permission to tune until green. Until then the result is research measurement only. Publish all cohorts and failures; no selected good frames as the entire evidence.

## Evidence record schema (future)

`claim_id`, `level`, `source_sha`, artifact/model/data/calibration SHA-256, exact platform/driver/firmware, command and dependency lock, clock provenance, conditions/partition, preregistered acceptance reference, metric values/uncertainty, `status` (`passed|failed|pending_external`), failure reasons, reviewer role and redacted artifact links. Hosted runs add immutable run URL; physical runs add rig/calibration records. CI skip is never a pass. [BASELINE](BASELINE.md) uses a limited Phase 0 execution record with raw negative evidence.

## Mandatory appliance gates

A01–A09 in [APPLIANCE-RUNTIME](APPLIANCE-RUNTIME.md) are additional required gates, mapped to P1.7 and later P4 hardware qualification. A01/A02/A08 explicitly prove the unit boots and keeps inference/local status without installer, external laptop/phone, remote viewer, WAN, cloud/control backend or license heartbeat. A03/A04/A05/A06/A07 cover power/sensor/zero-light/worker/resource/update faults. Fixed sensor buses/local LAN and power remain connected as appropriate; absence of an external programming USB host is not absence of all sensor wiring.

Software-level acceptance uses real service-manager VM boot plus recorded/virtual sensors, not unit-only startup. Physical brownout/ignition/temperature/uptime/zero-light accuracy require exact-rig evidence later. Initial software soak is one hour with published latency/drops/RSS and all failures; physical duration/environment thresholds are preregistered for each intended domain. Startup state is UNKNOWN until valid fresh evidence, and a reboot never restores old track state. Local device identity is for administration only, never person linkage.

## Executed Phase 1 candidate checks — 2026-10-08

Implementation source: `d90ae953f6431fd9d460e440432ac72825b8d250`. This is a local software candidate. The [acceptance record](evidence/phase1/acceptance.json) closes the completed appliance gate. Earlier checkpoint JSON files retain the original code/artifact hashes; the records below identify the newer artifacts.

| Milestone | Actual implementation and executed evidence | Qualification boundary |
|---|---|---|
| P1.1 | Separate core/edge wheels, doctor/replay/run/serve; fresh external Python consumers; [package](evidence/phase1/package.json) | Local artifacts; no PyPI publication |
| P1.2 | Strict raw parsing, closed Pydantic types, canonical OpenAPI and real output fixtures; full integration suite | Frozen core remains authoritative for temporal semantics |
| P1.3 | File/RTSP actual pixels through pinned detector, explicit offline pixel replay through registration/core, virtual UVC, clock/calibration/fault tests | Generic live exposure clock unqualified; no physical UVC/OEM claim |
| P1.4 | Real authenticated local HTTP/SSE processes, ownership/auth/Host/Origin/bounds, supervisor-owned zero-viewer processing, crash and update tests | Local loopback software; no remote TLS deployment claim |
| P1.5 | External Python client and packed Node TypeScript client, expiry/enum rejection tests, [Node result](evidence/phase1/node-consumer.json), native fixture handoff | Node executed; browser and native Swift/Kotlin integration pending |
| P1.6 | [48 integration tests](evidence/phase1/integration.json), reproducible wheels, both [CPU containers](evidence/phase1/containers.json), [SBOM](evidence/phase1/edge-sbom.json), [security review](evidence/phase1/security-review.json), fuzz and visual reproduction | Actual runner matrix below; hosted workflow has not run |
| P1.7 | Dedicated-account signed Linux image, real offline boot/reboot and worker/update harness, local status and operator guides | [Final hour gate passed](evidence/phase1/boot.json); physical A01–A09 qualifications remain pending |

Commands executed include `scripts/verify.py`, `scripts/check_ecosystem_plan.py --self-test` (18 negative probes), `unittest discover -s tests/integration`, TypeScript `npm test`, `scripts/edge_package_check.py`, `scripts/edge_pixel_service_e2e.py`, `scripts/edge_container_check.py`, `scripts/edge_node_e2e.py`, `scripts/edge_inventory.py`, both required core fuzzers, `scripts/verify_visuals.py`, `scripts/edge_reproduce.py` and `scripts/reproduce.py`. Use the installed project environment and documented fixture/tool downloads. Builds and external consumers do not use a product release registry.

### Executed versus pending matrix

| Environment | Executed | Pending / exclusion |
|---|---|---|
| macOS ARM64, CPython 3.13.15 | Full edge suite; actual OpenCV file/local RTSP; installed wheel/server/Python/Node; clean-clone and deterministic artifacts | Physical camera, Core ML, native Mac appliance integration |
| Linux ARM64 container on Docker VM | Installed HTTP/SSE, no network/read-only root/capability restrictions; signed update permission/exec boundary | Physical Linux camera/NPU/GPU |
| Linux AMD64 container, emulated on ARM host | Installed HTTP/SSE and zero-viewer processing | Native x86 timing and hardware |
| Linux ARM64 QEMU TCG guest | Real kernel/systemd boot, local synthetic source, no NIC/login/viewer, fault and offline update; one-hour gate passed | No physical standalone computer, power, thermal or optical claim |
| Windows x64/ARM64; macOS Intel; other Python/OS matrix cells | CI specifications/code paths only | Not executed; never counted as pass |
| Hosted GitHub Actions | Dedicated nonpublishing workflow prepared | No hosted run was triggered |

The frozen aircraft evaluation still contains 20 fixed-wing aircraft misses and 721 temporal false positives (0 true positives). These are not UAV-specific validation. Earlier adverse latency tails remain in the baseline, including the recorded 42,225 ms pixel-path maximum. Faster later core-only measurements do not replace those failures.

A fresh installed pixel/SSE check timed out under concurrent load at its unchanged 20-second client bound; its local log is retained and the unchanged focused repeat passed both file and RTSP paths, as recorded in installed-pixels.json. The candidate makes no hard real-time availability guarantee. Cold VM startup also exceeded the original 45-second observation window; the negative gate remained failed, and the final image uses a 120-second first-boot check plus the unchanged 3,600-second second boot.

Read [REVIEW](REVIEW.md) for the retained Queue/stop-token/permission counterexamples and remaining limits. Physical sensor clock calibration, zero-visible accuracy, power/thermal behavior, independent local hardware indication, field safety and external certification remain unqualified.

The actual second boot ran 3,600.66 seconds. Sampled synthetic processing latency: p50 8.513ms, p95 14.057ms, p99 17.034ms, max 87.603ms. Observed service cgroup peak: 123,715,584 bytes (about 118MiB); status record at most 347 bytes; journal 1,048,576 bytes. The report retains 89 mailbox overwrites, 208 busy-write rejections and 72 expired status samples; no uninterrupted-availability or zero-drop claim is made. Capture gaps are inapplicable to the synthetic source, and abrupt death can lose unpublished diagnostic increments.


## Autonomous P2 sensor checkpoint

[Sensor evidence](evidence/phase2/sensors.json) records bounded raw raster/cloud, rectified geometry and binary replay tests, with original synthetic inputs. The final sequential integration suite passed 62 tests in 240.478s. The earlier concurrent run failed one existing startup wait (61 tests); the unchanged isolated test passed. Both outcomes are retained, with no assertion/deadline change. Fourteen sensor tests include 2,000 corruption mutations. Plan integrity passes 23 negative probes; repository verification and Ruff pass. Both required fuzzers ran over 60 seconds with no unexpected exceptions; scoped [security review](evidence/phase2/security-review.json) records Bandit and limits.

These results add software contracts, not sensor SDK/node installation, calibrated nonvisible semantics, hardware qualification or a public release. New wheel and clean-clone results are bound in the P2 record, separately from immutable Phase 1 evidence. See [sensor contracts/provenance](P2-SENSOR-ADAPTERS.md) and [current authority](LATEST-OWNER-AUTONOMY.md).


Current P2 source checkpoint: `dd2328ee398b3d8177635914644a3ba326ab5386`. Clean-clone governance/plan checks, installed sensor/HTTP/SSE consumers and byte-identical wheels passed. Source archive and zipapp also reproduced, but **overall reproduction failed its frozen Mac latency gate**: p95 118.711ms, then unchanged synthetic retry 129.476ms, against 100ms. A separate offline Linux ARM container running identical core/evaluator bytes passed at p95 1.501ms. All outcomes, CPU timings, source hashes and the original aircraft failures are retained in [performance evidence](evidence/phase2/performance.json). Linux success does not replace the native Mac failures. Publication remains held; independent software implementation continues. Hardware/field qualification remains pending.
