# RescueSense remediation evidence — 8 October 2026

This document records changes after sealed v3 candidate `bd6fc88`. It supplements, does not rewrite, the frozen protocol, thresholds, historical failures or source-bound evidence. Everything below is **local macOS Apple Silicon**, not field or hosted verification.

## Browser execution: previously blocked, now executed

`scripts/browser_check.py` now tries the Playwright revision first and, **only if its executable is absent**, a previously installed macOS Chromium headless-shell from the local Playwright cache. It never suppresses a sandbox/launch/test failure. On this host, the test succeeded with cached `chromium_headless_shell-1247`: RGB blackout handling, expiry/UNKNOWN and coarse radar-mode UI assertions all passed. Actual PNG screenshots and a Playwright video were written under `build/browser/`; these are synthetic-scene visual checks, not device-camera evidence.

## Same frozen model, optional Core ML execution

`RGBDetector` keeps OpenCV as the default. Explicit `backend="coreml"` requires ONNX Runtime 1.30.0 and the Core ML execution provider; missing provider, wrong model SHA-256, wrong output shape, invalid values or malformed inputs fail closed. CPU may still execute unsupported ONNX nodes. No confidence thresholds, categories, classifier weights or AOT evaluation labels have been changed.

On the 27 independently evaluated licensed still/recorded frames in `scripts/coreml_evaluate.py`, CPU and Core ML output counts, classes, bounding boxes and scores matched the declared equivalence tolerances (27/27). Both empty-image negative and zero-visible-light suppression passed. Reference results in `build/coreml-comparison.json`:

| Measurement | OpenCV CPU | Core ML |
|---|---:|---:|
| Frame median (27 interleaved comparisons) | 686.009 ms | 64.517 ms |
| Frame p95 (27 interleaved comparisons) | 835.134 ms | 101.379 ms |
| Accelerated model load | — | 3091.003 ms |
| Accelerated first inference after load | — | 389.337 ms |

The interleaved Core ML **p95 failed** the 100 ms reference budget; that negative result is deliberately retained.
## Isolated complete recorded inference and replay

`RESCUESENSE_VISION_BACKEND=coreml .venv/bin/python scripts/vision_e2e.py` ran all 25 fixed AOT frames twice (determinism) through the original image preprocessing, pinned model, schema, registration and temporal replay. Warm per-frame inference results written to `build/vision-coreml/report.json`: **median 32.134 ms, p95 35.839 ms, maximum 39.715 ms**. Model construction was **3506.062 ms**, with an additional **438.543 ms** first inference, excluded from the warm 25-frame figures. All 25 warm frames were below 100 ms in this isolated execution; this is not a guaranteed frame deadline, a cold-start result, or a measurement of acquisition, sensor synchronization, controller latency, thermal throttling or power.

Recorded aircraft outcome stayed **0 true positives, 20 false negatives, 0 false positives**. This is a substantial *runtime* improvement, **not an object-detection accuracy improvement**. The frozen dataset contains fixed-wing aircraft, not known drones. The classical baseline with 721 false positives remains historical evidence. A newly trained, licensed and held-out-evaluated small-aircraft/UAV detector is still needed before an airborne detection claim.

## Remaining qualification blockers

- Real thermal, RGB, radar, active-depth, camera and vehicle/drone controller hardware were **not** exercised. Exact device/firmware, calibration, clock synchronization, day/night/zero-light, missing-data, power and hardware-in-loop defensive-response tests remain necessary.
- No representative held-out human/thermal/UAV detection evaluation, empirically calibrated uncertainty or independent privacy/safety review exists. Recorded 20 false negatives remain a failed accuracy result.
- Startup delay, environment-induced p95 variability, inference+capture freshness and T10 repeatability remain deployment limitations. Never waive the 100 ms age gate; stale evidence remains UNKNOWN.
- No remote is configured for this repository; hosted CI, security checks and signed/public releases remain unverified. Local checks must not be relabeled hosted verification.
- No production use, certified avoidance, live sensor fusion or real-world rescue detection is claimed.

Reproduction: `.venv/bin/python scripts/browser_check.py`, `.venv/bin/python scripts/coreml_evaluate.py` and `RESCUESENSE_VISION_BACKEND=coreml .venv/bin/python scripts/vision_e2e.py`. The model remains explicitly fetched and digest-pinned. No recorded data labels enter inference.
