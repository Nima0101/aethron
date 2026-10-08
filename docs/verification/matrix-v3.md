# Frozen v3 verification and evaluation protocol
Frozen before v3 source or evaluation. All earlier S/H rows remain applicable with owner-authorized semantics. No threshold changes after evaluation to pass. Correctness fixes retain counterexamples; specification changes require an explicit new version and reevaluation.

| Gate | Acceptance/evidence |
|---|---|
| T01 | Historical/v3 governance hashes, strict parser bounds, rejected prohibited fields/modes |
| T02 | RGB blackout retains same track/current box from valid LWIR/radar/depth; provenance changes; all loss UNKNOWN |
| T03 | Person occlusion <=500ms retains uncertain ID, then reacquires; expiry/reentry gets new ID; deletion/close/session/camera break tested |
| T04 | UAV intermittent misses, fast non-overlap motion, no prediction births |
| T05 | Camera translation and independent object motion separated; invalid transform withdraws motion; robust estimator outliers rejected |
| T06 | Timestamp skew/staleness/calibration/registration/duplicate/future frames, sensor disagreement and resource bounds |
| T07 | Crossing ambiguity cannot claim identity certainty; no embeddings/re-ID paths; permutation invariant geometry; assignment checked against brute force |
| T08 | Deterministic CLI replay twice; corruption fails closed; real recorded pixels -> independent proposals -> tracker -> metrics -> original visual path |
| T09 | Frozen synthetic sequences: measured detection precision/recall at IoU0.3, centre RMSE, ID switches, fragmentation, false positive/negative counts; temporal method no more ID switches than greedy-IoU baseline on isolated fast motion and occlusion, current-evidence recall>=0.90 on clean synthetic sequences, no phantom births. Crossing challenge reported separately, no perfect-association claim |
| T10 | Benchmark100 frames32 objects: p95 step<=100ms without tracing, tracemalloc peak<=32MiB; report p50/p95/max, platform/Python, no hard-real-time/power claim |
| T11 | >=2000 randomized assignment/state/schema cases; >=60s temporal byte/state fuzz; zero unexpected exceptions or privacy leaks |
| T12 | Full CLI/library/isolated-wheel/clean-clone/release reproducibility, pinned dependency/security/license/SBOM; v3 README/demo reproduction |
| T13 | Recorded AOT fixed excerpt: first20 consecutive annotated frames of first annotated flight in CSV, plus first5 empty frames as negative controls, chosen without detector results. No crop from labels; full-frame independent image proposals. Freeze bytes/hashes before evaluation, report every FP/FN/switch, require reproducible execution (no invented accuracy threshold). Poor performance blocks physical/class capability claims |
| T14 | Hosted real E2E including downloaded pinned recording, metrics, visuals, packaging. Actual run URL required, not workflow existence |
| T15 | Physical day/night/LWIR/fusion/UAV qualification and external privacy/safety review; exact devices and representative held-out data. Missing evidence blocks production |

Metrics choice: report separately observable detection/localization/association errors instead of a homemade HOTA approximation. HOTA is valuable for broad MOT ranking but its global assignment and threshold sweep add evaluator complexity; our small safety scenarios need auditable frame-level errors and explicit abstention. Use per-frame maximum-IoU one-to-one matching at0.3, count switch when GT's matched emitted ID changes; fragmentation when match resumes after a missed frame. Predictions count separately and cannot inflate observed recall. No field generalization from synthetic input or the tiny AOT excerpt. Baseline uses identical inputs and score/expiry limits with greedy IoU>=0.3 and no motion; retained negative outcomes must be published.

Detector hypothesis for recorded grayscale path: original dependency-free local-contrast connected components, no training/labels at inference. Bounded grayscale <=640x512, dark pixel <= local neighbourhood mean-20, 8-connectivity, component area3..1200, maximum32 proposals, fixed score0.6 (not calibrated probability). Semantic output obstacle only; cannot distinguish aircraft/drone/bird. This intentionally simple image baseline supplies real pixel E2E evidence, not semantic detector qualification. Do not rename aircraft ground truth UAV. Evaluation uses independently supplied annotations only after inference.

Freeze synthetic fixture generation rules before evaluation: 24frames at100ms, linear movement0.012 normalized/frame, box0.04x0.08, starts(0.10,0.45); fast UAV0.018/frame box0.012x0.016; translation -0.008/frame; misses frames8,9,16; blackout afterframe8. Additional crossing and all-loss/expiry negative scenarios. Classes cover all protocol enums. No tuning on recorded excerpt.
