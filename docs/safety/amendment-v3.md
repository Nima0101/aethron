# AETHRON Capability Amendment v3 — temporal perception, night operation, tracking and E2E evidence

This amendment expands AETHRON from frame-local detection into a real temporal perception system.

It is based on the owner request plus current external prior-art research, including Visage Technologies' 2026 UAV Detection PoC.

Preserve the existing prohibitions on biometric identity, cross-scene re-identification, covert person surveillance, target designation, weapon integration and autonomous person pursuit.

Do not interpret those prohibitions as a ban on legitimate short-horizon tracking required for perception, collision avoidance, rescue or UAV/vehicle situational awareness.


## Allowed temporal perception

The product MAY implement for permitted object classes:
- multi-frame tracking-by-detection;
- ephemeral track IDs within an active scene/session;
- track initialization/confirmation/termination;
- short occlusion bridging;
- bounded missed-detection persistence;
- Kalman/EKF/other justified state estimation;
- Hungarian/assignment-based association or a better justified alternative;
- IoU, L2, appearance-free geometric/motion association;
- motion estimation;
- short-horizon motion prediction;
- relative velocity and direction;
- camera/ego-motion compensation;
- temporal smoothing that preserves uncertainty;
- cross-sensor fusion for the same active object;
- track confidence / covariance / freshness;
- reacquisition only inside a bounded short-term window.

A track that expires or leaves the allowed temporal window must not become a durable person identity. Re-entry after expiry receives a new ephemeral track.

## Object classes

The architecture may support, when evidence and datasets justify each class:
- person / pedestrian;
- cyclist / micromobility;
- vehicle;
- UAV / drone;
- animal;
- obstacle;
- equipment / machinery;
- hot source;
- cold source;
- fire-like thermal hazard;
- smoke/haze cue;
- other non-biometric safety-relevant physical object classes approved by the same governance process.

Bounding boxes are permitted for these classes in line-of-sight or otherwise ordinary sensor-visible scenes.

Segmentation, depth overlays or trajectories may be added only when they improve safety/perception and remain inside the same non-identifying, non-targeting boundary.

## Day/night and zero-visible-light

Night operation is a first-class product capability, not a fallback demo.

Research and integrate where available:
- LWIR/thermal;
- RGB-T / multispectral fusion;
- radar/mmWave;
- LiDAR / active depth;
- NIR or other suitable active/passive non-visible-light sensors;
- IMU/ego-motion inputs;
- calibrated time synchronization across sensors.

When RGB is unusable in darkness, valid thermal/radar/depth evidence must be able to maintain the object/track, bounding box, confidence, range/motion estimate and safety state.

The system may withdraw a track only when the remaining validated evidence no longer supports it under predeclared acceptance criteria.

## UAV detection/tracking

UAV/drone detection and tracking is an explicit supported research/product track.

Study and compare:
- small-object thermal detection;
- low-SNR / few-pixel targets;
- thermal occlusion / solar loading;
- long-range confidence degradation;
- tracking-by-detection;
- FLIT-style L2 + IoU association;
- Kalman-based motion models;
- Hungarian assignment;
- camera-motion compensation;
- HOTA and other appropriate tracking metrics;
- embedded/edge latency and power constraints.

The system may keep an ephemeral UAV track while visible or briefly occluded. It must not integrate weapon engagement or autonomous attack.

## Broad research mandate

Research current primary/serious sources broadly before freezing v3 architecture.

At minimum inspect:
- the Visage Technologies UAV Detection case study/blog supplied by the owner;
- linked/related Visage material on edge AI, perception, autonomy and AI safety;
- source papers/repos for any algorithm adopted;
- relevant thermal/LWIR datasets and their licenses;
- RGB-T / pedestrian / automotive / UAV datasets with clear provenance;
- OpenCV and relevant tracking primitives;
- modern tracking-by-detection alternatives;
- ONNX Runtime / TensorRT / Core ML / mobile inference options where relevant;
- ROS 2 or equivalent robotics integration patterns where relevant;
- automotive perception safety and SOTIF/functional-safety guidance;
- edge hardware deployment patterns;
- current open-source perception stacks.

Do not copy a blog implementation blindly. Extract testable requirements and verify every adopted mechanism independently.

## Algorithms are hypotheses, not commandments

Kalman + Hungarian is explicitly allowed and should be implemented/evaluated if appropriate, but Astra must compare alternatives rather than cargo-cult the named stack.

For each selected method:
- record why it was chosen;
- define inputs/outputs;
- define failure modes;
- benchmark against at least one simpler baseline;
- retain negative results;
- measure latency/memory;
- test occlusion, fast motion, camera motion and dropped detections;
- freeze metrics before tuning on evaluation data.

No threshold may be changed after evaluation merely to pass a gate.

## Strict end-to-end CI

Astra must design a serious CI workflow that exercises the actual product path, not only unit tests.

CI/release gates should include, where applicable:
1. formatting/lint/type/static checks;
2. unit tests;
3. parser/schema/property tests;
4. tracker association tests;
5. deterministic recorded-sequence replay;
6. multi-frame occlusion and re-entry tests;
7. camera-motion compensation tests;
8. day/low-light/zero-visible-light replay;
9. cross-sensor fusion and sensor-loss tests;
10. tracking metrics on frozen evaluation sets;
11. thermal false-positive/false-negative reporting;
12. UAV small-object sequence evaluation;
13. adversarial/privacy/misuse tests;
14. fuzzing;
15. benchmark/latency/memory regression gates;
16. packaging/install/consumer tests;
17. clean-clone quickstart;
18. reproducible release build;
19. SBOM/license/provenance/security scan;
20. actual README/demo artifact reproduction.

Hosted CI may not be claimed until it actually runs remotely.

## Architecture ownership

Astra owns the repository structure and may refactor the current reference implementation substantially.

It may introduce additional languages/native modules, model runtimes or platform adapters only when evidence justifies the complexity.

Folder structure must emerge from clear subsystem boundaries, not cosmetic architecture.

Expected conceptual boundaries include sensors/adapters, calibration/time sync, detection/model runtime, tracking/state estimation, fusion, scene/track model, visualization, safety decisions, platform adapters, evaluation, fixtures/datasets, benchmarks, verification and release tooling.

Exact names and implementation language are Astra's decision and must be documented in ADRs.

## Production/live claim discipline

The goal is genuinely functioning live software.

However:
- recorded public datasets prove algorithmic behavior, not a specific physical device;
- simulation proves integration semantics, not hardware latency;
- real hardware claims require exact-device evidence;
- day/night claims require relevant physical or licensed recorded sensor evidence;
- phone/car/drone support is per-platform and per-hardware, not generic marketing.

Continue all independently verifiable work even when hardware is missing.

Never downgrade a missing live-hardware gate into "production-ready".

## Safety line for human tracks

Human/pedestrian tracking for immediate perception is allowed:
- ephemeral IDs;
- bounding boxes;
- confidence;
- range;
- velocity/direction;
- short-horizon path prediction;
- short occlusion continuity.

Still prohibited:
- face/gait/voice recognition;
- biometric templates;
- name/identity inference;
- re-identification after the bounded track expires;
- cross-camera/cross-location identity stitching;
- long-term person history;
- threat scoring of a person;
- autonomous following/pursuit;
- target designation.

This distinction must be explicit in schema, tests and README.

## Through-obstruction remains a different mode

Do not use this v3 expansion to turn coarse through-obstruction sensing into precise hidden person tracking.

Through-obstruction human output remains coarse zone/sector presence with uncertainty.

Ordinary thermal/RGB/radar/depth line-of-sight perception may use boxes/tracks as above.

Keep these two capability classes technically and publicly distinct.

## Required v3 tests

Add at least:
- persistent box through RGB blackout with thermal/radar/depth support;
- ephemeral person track across a short occlusion;
- new ID after track expiry/re-entry;
- UAV track across intermittent missed detections;
- fast-object association stress;
- camera-pan compensation;
- camera-motion vs object-motion separation;
- sensor timestamp skew;
- false association challenge with crossing objects;
- track deletion when evidence expires;
- no re-ID features/embeddings in the public person-tracking path;
- deterministic replay;
- benchmark regression gate;
- HOTA or other justified tracking metric on frozen sequences;
- explicit negative cases where prediction must not invent an object.

Retain failing counterexamples and document fixes.

This amendment supersedes any earlier rule that prohibited all temporal tracking, while preserving the identity/targeting prohibitions above.
