# Checked baseline — 2026-10-08

Starting commit: `59fda946771d4ac8c9d1b52eeb3d948215325e4c`; branch `feat/aethron-vehicle-uav-preparation-20261008`; worktree initially clean. Direct anonymous GitHub API retrieval confirmed this public main SHA. The camera PWA returned HTTP 200 and AETHRON HTML; this is reachability evidence, not a browser/camera/offline-cache test. [Public retrieval digests](evidence/public-retrieval.json), [S59](SOURCES.md#s59), [S60](SOURCES.md#s60).

## Inspected implementation and governance

Read root AGENTS, v3 amendment/protocol/matrix first, then README, pyproject, core/temporal/vision boundaries, existing scripts/workflows, constitution/no-cheating, status/failure/remediation/hardware/platform docs and frozen manifests. Preserve the [protected baseline hashes](baseline-protected.json), including historical governance, data/model freezes and current corrected AETHRON branding assets.

Existing code: `aethron` 0.2.0 pure Python core and CLI; strict v1/v2/v3 schemas; registered temporary geometry-only tracking; semantic thermal/radar/depth adapters; pinned optional YOLOX pixel model and explicit Core ML backend; `scripts/live_video.py` host preview; browser camera PWA. These are not a universal physical sensor-driver or OEM/UAS integration suite. The core explicitly excludes networking imports. Existing build/release scripts require clean committed source and already enforce independent package consumers and reproducibility.

Historical source-bound evidence is in [v3 status](../../verification/status-v3.md) and [dated remediation](../../verification/remediation-20261008.md). Those reports mix older qualification status with later updates: retain their exact dates/SHAs. In particular, the old statement that no public deployment exists was superseded by later public PWA work. Public availability does not close physical iPhone/night sensing or safety gates.

## Fresh local executions

[Machine-readable checks](evidence/checks.json) record commands, status and limitations. Local environment: macOS arm64, system Python 3.9.6 for baseline semantics; isolated project tool environment Python 3.13.15 for build/Pillow/security. No other worktree/toolchain/cache was used for source edits.

| Check | Result |
|---|---|
| `scripts/verify.py` | PASS: 66 tests, frozen hashes, content/links, dataset, import consumer, actual deterministic CLI replay |
| Temporal evaluation | PASS frozen software gates; core p95 13.547 ms, max 14.654 ms, peak 114534 traced bytes; actual pixels remain 20 FN/721 FP/0 TP |
| Temporal fuzz | PASS: 44935 cases, at least 60 seconds, no unexpected exceptions |
| Legacy fuzz | PASS: 29256 cases, at least 60 seconds, no unexpected exceptions |
| Isolated wheel build/install | PASS: byte-identical builds, external wheel consumer, fixture tracking; artifact digest retained |
| Bandit runtime scope | PASS: zero findings; not an independent audit or native decoder scan |
| Synthetic visual generation | Executed successfully |
| Visual artifact reproduction | **FAIL**, `perception-day.png`; retained and investigated below |
| Clean clone/release reproduction | PASS for unchanged committed baseline 59fda94; uncommitted plan verified separately |
| Hosted, hardware, native iOS, live sensor/model qualification | Not run here |

Reports: [temporal](evidence/temporal.json), [temporal fuzz](evidence/temporal-fuzz.json), [legacy fuzz](evidence/legacy-fuzz.json), [wheel](evidence/wheel.json), [Bandit](evidence/bandit.json).

## Negative results remain authoritative

The recorded AOT test is fixed-wing aircraft, not verified UAV. Fresh classical detector result remains 20 misses and 721 false positives; inherited YOLOX evidence has the same 20 misses with zero positives. Positive stills and synthetic tracking do not qualify an airborne detector. Historical p95 298.116 ms and 123.829 ms core failures remain in the original record. A fresh core-only pass does not prove stable system latency. Prior RGB CPU inference was far above the 100 ms freshness gate; prior Core ML had both a failed interleaved p95 and a faster warm isolated run, with substantial cold start.

## Inherited visual reproduction failure

Pinned Pillow 12.3.0 generated all artifacts to an ignored build directory. The existing strict verifier failed on `perception-day.png`. A full byte comparison found four PNGs, GIF and manifest unequal; input JSONL, output JSON and HTML equal. All four PNG pixel differences are confined to rectangle `(26,27)-(478,51)`, the title text region. Git commit `d3287ed` changed the generator title from the old project name to AETHRON. This strongly identifies stale pre-rebrand raster artifacts as the cause; no raster assets or generator were changed in Phase 0. The exact failing test remains open rather than being reclassified as a pass.

[Original sanitized failure](evidence/visual-failure.txt), [all byte comparisons](evidence/visual-comparison.json), [pixel-difference regions](evidence/visual-pixel-diff.json). P1.6 requires retaining this counterexample, confirming the generator/artifact relationship and repairing reproducibility while preserving the corrected official logo. No publication gate waiver.

## Verification limits

No physical camera, vehicle, drone, actuator, simulator fleet or hosted CI was operated. No thermal/UAV training or third-party model download occurred. No generic public API endpoints, cross-platform SDKs or container deployment were exercised because these are planned work. Tool environment dependencies were installed only in this worktree's ignored build directory; source changes are the planning documents/checker/workflow. Runtime logs remain local; committed evidence is redacted and source-bound.

[Baseline clean-clone/release report](evidence/baseline-clean-clone.json) and [clone temporal report](evidence/baseline-clone-temporal.json) preserve the actual source revision and metrics. The clone does not contain uncommitted planning additions.
