# ADR 0007 — bounded scene world model v1

Date: 2026-10-09. Scope: dependency-independent P6 software.

## Requirements and research

Consume the existing v3 observation, state and provenance contracts; retain only
scene-local geometry for immediate safety. Quarantine unsupported frames/clocks,
preserve sensor-loss evidence, and expose no actuation or persistent identity.

Primary sources reviewed before implementation:

- [ROS REP 105](https://github.com/ros-infrastructure/rep/blob/master/rep-0105.rst)
  distinguishes map, odom and platform coordinates. Existing normalized image
  boxes cannot justify any of these physical frames without additional transforms.
- [ROS 2 clock design](https://design.ros2.org/articles/clock_and_time.html)
  separates steady/system/simulation clocks and requires handling time jumps.
  A timestamp alone cannot establish a compatible epoch or synchronization.
- [Python copy semantics](https://docs.python.org/3/library/copy.html) explain why
  nested output aliases need tests. Session already constructs detached outputs;
  P6 stores no output cache and retains diagnostic strings in an immutable tuple.
- [Rust Serde](https://serde.rs/) provides typed serialization; a Rust boundary
  would also require an FFI/IPC or duplicated v3 runtime for this component.

## Decision and alternatives

Use Python 3.9+ standard library composition around the existing strict v3 parser
and Session. Selection follows bounded input (64 detections, 32 tracks), no new
numerical estimator, direct contract reuse and no deployment/runtime dependencies.
Language continuity alone is not the criterion. A Rust/Serde implementation can
be reconsidered with measured isolation or latency requirements. ROS 2/tf2 is
appropriate for qualified physical transforms, but those inputs are unavailable
here. No transform or timing synchronization is inferred.

The simpler baseline is direct Session use. Compare canonical scene outputs on
the frozen synthetic sequences, permitting only IDs to be renamed by occurrence.
New behavior is context quarantine and cross-call clock/frame high-water checks.
No change to fusion thresholds, association, uncertainty or frozen evaluations.

## Design and execution plan

The versioned [boundary contract](../architecture/world-model-v1.md) is additive;
v1/v2/v3 and their freezes remain unchanged. Implementation is single-agent.

1. Write failing boundary tests for unsupported metadata, time regression after
   watchdog/errors, stale/future frames, quarantine recovery and privacy.
2. Implement one in-memory WorldModel composing Session, retaining only scalar
   watermarks, a defensive contract and bounded current diagnostic reasons.
3. Compare frozen simulation outputs to Session, test blackout/loss, calibration,
   mutation isolation, identity expiry and capacity; run focused lint/security.

Review focus: watermark loss after rejection; recommendation weakening after
rejection; expired provenance; output aliases; unsupported physical frame claims.
No local VM, container, clean clone, full fuzz or full repository matrix.
Hosted gates remain necessary before merge; simulation proves software semantics
only, not physical sensor capability or rescue suitability.
