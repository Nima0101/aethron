# Next executable work — autonomous software delivery

The [latest owner directive](LATEST-OWNER-AUTONOMY.md) supersedes the earlier Phase 1 stop/publication prohibition. P1.1–P1.7 remain complete on their recorded software matrix. Continue without another approval request, with no subagents or edits to the separate native iOS lane.

1. Complete P2.1 sensor integration: use the new bounded packet/replay primitives in a read-only ROS 2 Image/CameraInfo/PointCloud2 bridge, with explicit clock mapping, calibration invalidation, loss tests and installed consumers. Research/pin actual SDK interfaces and licensing before adding vendor-specific drivers. Keep recorded clocks distinct from trusted live acquisition.
2. Execute independent P2.2 rights/split/model evaluation and P3 platform/telemetry tasks when their dependencies permit. Preserve the fixed aircraft misses/false positives and frozen protocol. Do not turn raw thermal counts or radar points into invented class detections.
3. Prepare software-accessible P4 qualification capture/validation tooling. Physical rig/domain/certification gates stay pending. P5 hardware control remains excluded; only admissible non-actuating software work can proceed.
4. Run repository, installed package, security, artifact reproduction and relevant matrix checks. Then push/review via normal GitHub CI and merge only when legitimate prerequisites pass; verify the established Pages path after publication. Package release still requires rights/signature/reproducibility conditions. Never bypass a failing gate.

[Sensor contracts](P2-SENSOR-ADAPTERS.md), [machine status](PHASES.json), [execution ledger](EXECUTION.md) and [backlog](IMPLEMENTATION-BACKLOG.md) identify completed and pending work. Missing physical hardware does not block software adapters or replay/SITL. Current work is not globally qualified or publicly delivered.
