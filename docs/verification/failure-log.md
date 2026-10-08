# Retained failures and limits
- Initial core tests: 18 assertion failures and 2 missing-module errors before implementation. Initial adapter/CLI tests: 2 failures and 2 missing-module errors. Initial seven v2 tests rejected unsupported version 2 before implementation. These are recorded test-first states, not passing evidence.
- First synthetic evaluation paired alternating truth with lighting, leaving no positive zero-visible examples. Retained `examples/evaluation-v1.jsonl` and `evidence/synthetic-evaluation-v1.json`; strengthened coverage in protocol v2 without changing acceptance thresholds.
- Initial Ruff run found formatting/import/style issues, fixed before final checks. No tests were removed.
- Initial dependency audit could not create its default user cache under sandbox permissions. Re-run with project-local `--cache-dir build/audit-cache`; no elevated access or dependency safety exception used.
- Model and cues remain synthetic/external-unverified. No physical hardware proof, empirical probability calibration or independent safety/privacy review is available.
- Chromium launch failed before rendering: macOS MachPortRendezvous bootstrap registration was denied with code 1100. Real-browser screenshots/video/timer checks remain blocked; actual CLI capture and SVG unit checks are distinct evidence.
- Camera inventory (`system_profiler SPCameraDataType -json`) returned an empty list. No camera, thermal/depth/radar device or live sensor stream was exercised.
- Final adversarial review exposed legacy-v1 provenance retaining blind/dropped sensors in sources. Added a failing regression before fixing both protocol versions; supporting sources now exclude invalid evidence and confidence degrades. ADR 0003 records this safety tightening. Earlier captures/fuzz precede the correction; final evidence is regenerated.
- Cross-platform export review reproduced a CLI SVG failure under an ASCII console encoding (`UnicodeEncodeError`). Added a regression first; SVG stdout now writes explicit UTF-8 bytes. This fixes the transport encoding without claiming an untested OS is supported.
- USB inventory (`system_profiler SPUSBDataType -json`) also returned an empty device-name list; no serials or raw sensing were collected.

## v3 retained counterexample — stationary association, 2026-10-08
Initial temporal tests failed blackout single-sensor continuity and low-score continuation. A numerically identical stationary box produced IoU slightly above1 due floating arithmetic, then a tiny negative assignment cost rejected the update and cleared state. Clamp mathematical IoU to[0,1]; retain both tests. This changes no frozen threshold. Initial result15/17; rerun recorded after fix. No benchmark or recorded-data evaluation preceded this fix.

## v3 recorded-data negative result and follow-up
The frozen first25 AOT frames were selected before detector evaluation. Initial unregistered baseline missed20 aircraft with800FP; accepted translation transforms subsequently enabled actual temporal association, leaving20FN/721FP. The original result remains in evidence/v3/initial-unregistered-evaluation.json. No detector threshold changed. A separately preregistered YOLOX RGB adapter also missed all20, with0FP. Both results block airborne qualification. Positive person/animal still-image smoke checks passed; they are not field validation.

## v3 snapshot expiry review
A review found that global snapshot expiry could exceed a constituent claim's calibration deadline even though track expiry was correct. Global expiry now takes the minimum claim deadline. The30ms calibration regression test checks both outputs and subsequent UNKNOWN. No frozen threshold changed. Final evidence must be regenerated after this fix.

## v3 adversarial numeric review
Finite subnormal rectangles can have zero floating-point area. IoU now returns conservative zero overlap for zero union rather than dividing by zero. Output preserves positive measured extent instead of rounding tiny widths to zero. The new1e-300 rectangle test is retained. This numerical safety correction changes no detector/association acceptance threshold. Final fuzz, metrics and artifact reproduction are rerun because runtime geometry changed.

## v3 release hygiene review
Release cleanliness previously ignored untracked files. The candidate builder now rejects an untracked source addition, with an actual clean-clone rejection probe before the two successful builds. This prevents a locally tested source file from silently disappearing from an artifact.

## v3 malformed-stream contract preservation
Final CLI review found that malformed replay input reached the generic CLI WARN error after a vehicle STOP contract had already been established. The session itself failed closed correctly, but the CLI lost that contract. A sanitized ReplayError now carries only the last permitted fail-safe action; the actual subprocess corruption test requires UNKNOWN plus STOP and no payload echo. Before any parsed contract, WARN remains the only known fallback. No arbitrary input/action fields are forwarded.

## v3 scene-state minimization
A final privacy review removed the process-lifetime ordinal counter from reset/close state. Each new random scene namespace now starts its local counter at zero, so suffixes do not reveal counts across scenes. This is privacy tightening, not a correspondence/metric threshold change. The close-state test now verifies that counter deletion. Replay canonical IDs and detector/association geometry are unchanged; final source-bound fuzz and clone checks are refreshed.

## v3 clean-clone latency failure retained
Candidate acdb3a7 passed core/CLI verification but failed T10 in the clone:100frames/32objects, wall p50173.902ms, p95 298.116 ms, max326.698ms, traced peak116,289bytes. Frozen limits remain100ms/32MiB. Prior local runs were faster; this result is not discarded as a pass or relabeled CPU time. Add process-CPU timing only as a diagnostic and remove redundant overlap/innovation work for already-ineligible same-sensor/far/class-mismatched pairs; compare outputs before/after. Evaluation now writes its complete report before failing the same unchanged gate. Clean-clone tooling continues independent packaging/reproducibility checks after an evaluation failure but returns nonzero and records the failed gate. No performance waiver.

The redundant-work optimization preserved all frozen sequence outputs exactly. Its measured follow-up still failed the wall budget: the captured report records p50 30.757 ms, p95 123.829 ms, max185.356ms, CPU p9513.142ms and117,065 traced bytes. The diagnostic gap does not excuse the failure; cause is unestablished. The exact report is retained as optimized-latency-failure.json. No threshold, metric, fixture or accepted detection was altered.

## Final source-bound results
Candidate9fd150a passed66 tests and the latest clean-clone T10 execution (wall p95 70.188ms, CPU diagnostic11.215ms); earlier latency failures remain retained. Both60-second fuzzers passed on identical final runtime hashes. Source/zipapp/wheel builds reproduced, isolated consumers and original README artifacts passed. The RGB thread-profile experiment did not satisfy100ms and cannot close live inference qualification. No public push, hosted CI, physical sensing or production claim followed.
