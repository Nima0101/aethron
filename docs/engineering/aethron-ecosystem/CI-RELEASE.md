# CI and release specification

The new `aethron-ecosystem-preflight.yml` is a planning-integrity workflow. It is prepared and checked locally; no hosted execution is claimed. Existing workflows remain unchanged. Phase 0 cannot publish, deploy, sign a public release or claim a green production pipeline.

## Preflight implementation

Use immutable checkout/setup-python action SHAs inherited from existing workflow pins, read-only `contents`, `persist-credentials: false`, PR/push path filters for this planning area/checker/workflow, manual dispatch, and a short timeout. Python 3.13.15 runs the standard-library checker and negative self-tests without installing application dependencies. Pins and their local provenance are recorded in [versions.json](versions.json). A missing document, broken relative link/anchor, invalid JSON, floating selected version, missing source reference or changed protected hash fails.

## Future product CI matrix — SPEC ONLY

| Lane | Required tests | Evidence policy |
|---|---|---|
| Linux x86_64 CPython 3.9/3.13 core | parser/unit/property/fuzz/CLI/replay, wheel and zipapp consumers | Retain command, SHA, platform, outputs; maintain declared core Python floor |
| Linux arm64 core+edge | actual native install and replay/service E2E | QEMU build smoke distinct from native performance; native runner needed for timing |
| macOS arm64 core+edge | wheel, local server/client, AVFoundation adapter fake/recorded path | Native iOS build excluded from this lane; exact hardware camera test separately labeled |
| macOS x86_64 | core/edge consumer; supported native dependency wheels | If runner unavailable, pending evidence, not passing skip |
| Windows x86_64 | CLI UTF-8, paths, install, Media Foundation source, server/client/shutdown | Real Windows jobs required; Linux emulation insufficient |
| Windows arm64 | wheel/provider availability probe, native consumer | Initially experimental; unavailable dependencies explicitly block support |
| GPU/NPU/provider | model digest/equivalence, cold/warm E2E latency, RSS/VRAM, failures | Dedicated exact-device job; no “GPU supported” from CPU fallback |
| ROS 2 / PX4 SITL | pinned Humble/PX4/Agent/messages, camera+clock+loss | No physical flight or control authority inferred |
| ArduPilot/Parrot/vendor | isolated simulator/authorized SDK compile/recorded stream | SDK and firmware tuple, terms, scope, pending hardware status |
| HIL sensors/vehicle/UAS | calibration, clock, environmental/power/fault campaign | Manual controlled authorized rig, separate from untrusted PRs |

Use pinned OS/container/toolchain manifests and hash-locked dependencies at implementation time. Do not invent unavailable hosted runner labels. Mark matrix availability in machine evidence (`executed`, `failed`, `pending_external`, `not_applicable` with reason); aggregate product gate fails when a required lane is pending. Never use `continue-on-error` to hide a qualification failure. CI simulator lanes must not gain host serial/CAN devices or flight network routes.

## Tests in order

Static/lint/type → unit/strict parser/schema/property → adversarial/fuzz → deterministic licensed pixels-to-proposals-to-core-to-UI replay → actual installed HTTP/SSE clients → sensor-loss/clock/registration/expiry → frozen metrics and separate performance → isolated install/clean clone → artifact reproduction → SBOM/license/dependency/security review. Independent lanes may run concurrently; benchmark resource contention must be recorded. Model inference accuracy and software protocol correctness are different gates.

## Release gates, after separate publication authorization

1. Frozen governance/dataset/model checks and all relevant T01–T15/publication prerequisites evaluated with actual evidence; pending physical qualification limits product claims even if a research software release is permitted by governance.
2. Source-bound clean clone and installed wheel/sdist/zipapp/container consumer from outside checkout; no local cache or PYTHONPATH dependence.
3. Rebuild reproducible artifacts twice, compare hashes, retain negative build results. Verify source archive contents, notices, model provenance and SDK/data distribution rights.
4. Hosted CI URLs and signed provenance bind the exact tag/source/artifact. Produce SBOMs for core, edge, models and platform runtime images. Scan dependencies using a dated advisory source and document residual findings.
5. Protected publishing environment, narrowly scoped trusted-publisher/OIDC permissions, package-name ownership verification and owner review of a concrete candidate. No write token available to ordinary PR jobs.
6. Signed update manifest with rollback/migration compatibility; installer verifies signature/digest before replacement. Publish support matrix with measured limitations and negative data, then run anonymous installed-consumer checks against the actual release.

Publication and production qualification are distinct: a labeled research package can be useful, but cannot assert certified safety or unsupported hardware. The existing publication rules decide whether a specific research release is permitted; this plan does not waive them. [Fresh visual reproduction failure](BASELINE.md) is an open gate, not a cosmetic exception.

## Required appliance CI/release lane

P1.7 adds a pinned Linux boot-VM image lane: install candidate service/image, enable normal boot, remove provisioning channel, disable WAN, reboot without login and inspect independent local evidence. Repeat with no API subscribers and worker/model/config faults; simulate interrupted updates and disk-full. Execute actual native amd64/arm64 appliance consumers when runners are available; emulated boot validates semantics but not hardware timing/power. Include signed-image manifest verification, service-unit syntax, local notifier, bounded restart and offline update/recovery outputs. No current workflow runs this future product gate. A required unavailable boot runner is pending, not a green skip.
