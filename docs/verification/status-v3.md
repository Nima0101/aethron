# v3 evidence status — local candidate, not production-ready
The owner amendment and pre-implementation protocol/metrics were frozen in commit86b6117. Historical v1/v2 freezes remain byte-identical, including archived AGENTS. Additional image-registration and optional RGB-model hypotheses were frozen before their evaluation. No evaluation threshold was changed to make a result pass.

## Sealed local candidate evidence

[Machine-readable verification](evidence/v3/verification.json) binds the results to [runtime/test hashes](evidence/v3/runtime-manifest.json). Candidate9fd150a passed66 tests on local Python3.9.6 and3.13.15, actual CLI and recorded replay, isolated wheel/zipapp consumers, clean-clone quickstart and byte-identical release builds. The final clone benchmark passed at p95 **70.188 ms** (CPU diagnostic11.215ms, peak119,695 traced bytes). Prior123.829ms and298.116ms wall failures remain public: the latest pass does not establish stable deployment latency.

Final fuzz: **36,644 temporal cases/60.021s** and **17,527 legacy cases/60.017s**, no unexpected exceptions. Original48-frame synthetic CLI visuals reproduced byte for byte. All25 AOT frames were re-downloaded from their original URLs, hash-verified, transformed and reproduced exactly. Static/dependency audits reported no findings/known vulnerabilities in the checked scope. Measured coverage is90% for the current unit process plus actual RGB smoke inference; CLI subprocesses are separately tested end to end. [Coverage details](evidence/v3/coverage.txt). These are bounded checks, not independent certification.

Evidence: [tracking/recorded metrics](evidence/v3/temporal-evaluation.json), [clean clone/release](evidence/v3/reproduction.json), [wheel](evidence/v3/wheel.json), [model](evidence/v3/model-evaluation.json), [positive smoke](evidence/v3/model-smoke.json), [temporal fuzz](evidence/v3/temporal-fuzz.json), [legacy fuzz](evidence/v3/legacy-fuzz.json), [security](evidence/v3/bandit.json), [dependency audit](evidence/v3/dependency-audit.json), [vision inventory](evidence/v3/vision-supply-chain.json).

## Measured outcomes
| Scope | Actual result | Meaning |
|---|---|---|
| Synthetic clean/blackout/camera-pan |24/24 observed detections, zero switches | Controlled tracking/fusion semantics only |
| Synthetic fast UAV |21 observed matches,3 misses;0 switches vs20 greedy-IoU | Motion association benefits this fixture; not UAV detector accuracy |
| Synthetic occlusion |21 matches,3 misses;0 switches vs2 greedy-IoU | Predictions do not inflate observed recall |
| Synthetic crossing |46/48 matches,2 uncertain withdrawals,0 switches vs2 baseline | Explicit ambiguity costs recall; no perfect-association claim |
| Recorded AOT classical path |20FN,721FP,0TP over25frames | Failed airborne proposal detector; retained publicly |
| Recorded AOT optional YOLOX |20FN,0FP,0TP | Small-aircraft detection remains unqualified |
| RGB positive stills |Expected person and animal classes detected | Integration smoke only, common images may overlap training |
| Background translation on AOT |20/25 frame transforms accepted | Translation-model gate, not calibrated physical ego-motion |
| Initial32-object benchmark (Python3.13, macOS arm64) |p9516.343ms, peak117,907 traced bytes | Below frozen100ms/32MiB; not hard real time, sensor latency or power |
| Initial temporal fuzz |256,663 cases/60s, no unexpected exceptions | Bounded mutation/state exercise; not proof against all attacks |

The recorded learned model is not a thermal/UAV model. The classical pixel detector takes roughly a second per frame on this host; the tracking-core benchmark excludes image inference and must not be advertised as whole-system frame rate. Both aircraft failures block airborne detection qualification. No model was retrained or threshold adjusted on this excerpt.

## Gates and remaining evidence
T01–T07 semantics, T09 frozen tracking comparison and parser/assignment properties have passed locally. T10 stability remains unqualified despite the latest passing clone run: the clean-clone run reached p95298.116ms; redundant-work removal preserved every frozen sequence output but a subsequent run still measured p95123.829ms against100ms, with CPU p9513.142ms. The CPU diagnostic does not replace the wall gate. Earlier faster results remain in the table above; variability is unresolved. T08 recorded pixels and actual CLI replay execute. T11 final source-bound fuzz and T12 local packaging/clean-clone/visual reproduction passed and are recorded above. Prepared workflows are not hosted execution.

Exact blockers (including an unresolved local gate):

- T10 had wall-latency failures above the frozen100ms limit on this host before the latest passing run; no performance waiver. Preserve both negative reports. CPU/wall divergence is measured, but the underlying scheduling/environment cause has not been established.

- No exercised RGB camera, LWIR, radar, LiDAR/depth, NIR, IMU or robot/controller. Device inventory previously returned no camera/USB devices. Need exact model/firmware/calibration/time-sync, day/night/zero-visible scenes, missingness, latency/power/range and hardware-in-loop fail-safe results.
- The pinned RGB model took832–4202ms per frame in the recorded integration run on this host. A fixed1/2/4 CPU-thread experiment also remained above100ms (best measured median651ms); detections were identical. It cannot supply fresh live RGB evidence under the frozen100ms age limit here. Acceleration or another independently validated model/device would require new evidence. [Thread experiment](evidence/v3/vision-thread-profile.json).
- No representative held-out physical thermal/RGB-T/human/UAV evaluation, trained thermal/UAV model or empirically calibrated confidence/covariance. AOT and two stills do not substitute. The observed aircraft failures are a performance gap, not merely unavailable hardware.
- No independent privacy/safety review or system/controller assurance. Native inference cannot guarantee deadlines; downstream expiry/watchdog must be validated on the deployment.
- No hosted CI/security/anonymous clone result, published tag or signed hosted provenance; no remote/public push occurred. Local clone and unsigned artifacts cannot close T14/H01/H04.
- Browser execution is blocked by the recorded Chromium MachPort bootstrap denial in this sandbox. Directly generated GIF/PNG artifacts do not close browser timer/screenshot execution evidence.

Publication remains a prepared local candidate. Production remains blocked. No claimed live platform exists. See the preserved [legacy hardware record](hardware.md), [frozen v3 matrix](matrix-v3.md), [production gate](production-gate.md) and [publication gate](publication-gate.md).

**Post-seal update (8 October 2026):** The previously blocked browser verification now runs successfully against installed Chromium. Optional ONNX Runtime Core ML executes the same pinned RGB model substantially faster on the local Apple Silicon host, with CPU-equivalent outputs on 27 test images; its interleaved p95 still failed 100 ms, while a separate isolated warm 25-frame replay passed. Cold start and the original 20 aircraft misses remain. See the [dated remediation evidence](remediation-20261008.md). No field or hosted qualification is added.
