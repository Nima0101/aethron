> Historical v0.1 evidence/procedure. See the [current v3 record](status-v3.md).

# Gate status — 2026-10-08
**P6: local reference software verified. P7 publication blocked. Production readiness blocked.** No remote, public push, release tag, hosted pass or live-hardware claim exists.

Current safety rules are owner amendment v2 plus ADR 0003's universal honest support attribution. Original pre-source freeze and v1 AGENTS bytes remain preserved. Runtime requires Python 3.9+; optional wheel build tooling requires Python 3.10+ (tested with 3.13.15). These are separate runtime/build claims.

| Gate | Status and evidence |
|---|---|
| S01 governance | Passed: verify.py checks four hash manifests and the exact historical AGENTS relocation; owner v2 explicitly supersedes only the blanket human-box ban |
| S02 research | Passed for documented scope: current primary sources, alternatives, name/portfolio check; no novelty/standards-conformance claim |
| S03 strict protocol | Passed locally: closed schema, duplicate/unknown/type/numeric/nesting/byte/record/sample/geometry tests, including Python -O |
| S04 timing/calibration | Passed locally: skew, stale/future observations, expired calibration, dropped frames and unsupported combinations |
| S05 degradation | Passed locally: darkness/active-depth distinction, saturation/occlusion/noise/multipath, disagreement and surviving independent evidence |
| S06 model/resources | Passed for rule artifact/reference boundary: SHA-256 pinning, bounded model read, invalid model and adapter-reported timeout tests; actual upstream inference deadlines unqualified |
| S07 privacy | Passed for software boundary: no identity/association/history fields, no raw exports, authorized coarse-only obstruction, concurrent/re-entry isolation |
| S08 actions | Passed for fixtures: five bounded recommendations, expiry and UNKNOWN defensive behavior; no actuator integration |
| S09 properties/fuzz | Passed locally: 2,400 deterministic reference/permutation/withdrawal trials; 60-second parser/adversarial fuzz, zero unexpected exceptions |
| S10 evaluation | Passed for synthetic reporting: 320 current fixtures, all FP/FN/UNKNOWN retained; prior flawed corpus preserved. No real detector accuracy claim |
| S11 security | Passed locally: Ruff, Bandit, dependency audit, exact public-content/link scan, same-author adversarial review; no unresolved high/critical software finding established |
| S12 clean consumer | Passed locally: fresh Git clone, README commands, isolated zipapp consumer and public adapters |
| S13 release | Passed locally: two byte-identical source/zipapp builds, manifest/checksums/SBOM/unsigned provenance; duplicate wheel builds and isolated install |
| S14 presentation | **Blocked in part:** original vectors, 22 real CLI-executed synthetic scenarios, measured asciicast and explicitly rendered GIF replay exist. Sandbox denied Chromium; real-browser rendering/timer/screenshot/video evidence is absent |
| S15 repository | Prepared and locally inspected: license/notices, OSS guidance/templates, pinned CI/CodeQL/artifact workflows. Hosted execution unrun |
| D01–D05 | Passed as synthetic software behavior across all four light modes, thermal/radar fallback, disagreement and complete sensor loss |
| D06 | Core/SVG expiry and geometry checks passed; **real-browser timer validation blocked**, part of S14 |
| D07 | Reproducible darkness demos/README present; browser presentation check remains blocked |
| V2-1–V2-7 | Passed: human envelope continuity, honest provenance/confidence, expiry, no identity reuse/re-identification, UNKNOWN/fail-safe and coarse-only through-obstruction |
| H01 | **Blocked:** no public repository/hosted CI/security execution or anonymous public clone |
| H02 | **Blocked:** no exact-device/firmware/calibration/physical-darkness/latency/power or controller hardware-in-loop evidence |
| H03 | **Blocked:** no qualified learned person detector, consented representative physical dataset, empirical calibration, or independent privacy/safety assessment |
| H04 | **Blocked:** no tag, hosted attestation or downloaded public release verification |

Local evidence: macOS arm64, Python 3.9.6 and 3.13.15; 43 tests, no intentional skips. The coverage report measures only the parent process: CLI/demo subprocesses are exercised but appear uncovered. Do not turn line coverage into safety assurance.

Evidence files live in [evidence](evidence); [implementation manifest](evidence/implementation-manifest.json) binds runtime/test bytes. [Reproduction report](evidence/reproduction.json) names its source revision; final generated `dist/provenance.json` binds the packaged candidate. Reporting-only commits do not invent previous checks on new bytes; final clean-clone output is retained locally alongside release artifacts.

## Exact actions to unblock

1. In an environment permitted to start Chromium, install the pinned development tools and browser, run `python scripts/browser_check.py`, inspect resulting screenshot/video and expiry behavior, and resolve any findings. Current error: macOS MachPortRendezvous bootstrap registration denied, code 1100. No permission bypass attempted.
2. Repeat candidate software checks and current name/portfolio review before any public push. Then execute actual hosted CI/CodeQL and anonymous-clone checks before tagging/attesting.
3. Supply named thermal/depth/radar/camera devices, reviewed detector/model/data provenance and representative consented physical scenes. Complete the [hardware protocols](hardware.md) and independent safety/privacy/controller review. Empty camera enumeration is not evidence of any other sensor's availability.

No independent software task is waived because hardware is unavailable. Browser evidence and physical/hosted evidence remain explicit external blockers. See [failure log](failure-log.md) for retained negatives.
