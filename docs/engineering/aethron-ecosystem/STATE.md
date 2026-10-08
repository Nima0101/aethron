# Current state — 2026-10-08

Phase 0 is committed and complete. Phase 1 is expressly authorized; P1.1–P1.7 implementation exists on `feat/aethron-vehicle-uav-preparation-20261008`. P1.1–P1.6 software-candidate gates passed on the executed matrix. P1.7’s final one-hour boot/update soak is in progress. Reviewed runtime commit: `d90ae953f6431fd9d460e440432ac72825b8d250`. [PHASES](PHASES.json) and [EXECUTION](EXECUTION.md) carry machine status and checkpoint history. Phase 2–5 remain planned and unauthorized here.

Implemented: separate GPL-3.0-only `aethron-edge` wheel/CLI, strict OpenAPI/contracts, file/UVC/RTSP source ABI, monotonic capture admission/calibration, pinned detector replay, independent supervisor, scoped local HTTP/SSE, Python/TypeScript clients, signed offline runtime/update slots, systemd boot image and actual Linux VM harness. The normal appliance does not depend on a viewer, provisioning host or WAN.

Evidence already obtained includes installed consumers outside checkout, byte-identical wheels, real file/RTSP decode and pixels, strict/security/lifecycle/update tests, frozen governance checks and retained aircraft misses. The current running VM tests software boot/reboot, crash recovery, offline signed update and one-hour soak. It is not a physical sensor rig.

Unqualified: exact OEM/device/firmware tuples, physical UVC, zero-visible optics/accuracy, power/thermal/environmental behavior, real-world safety and certification. Windows/macOS Intel/hosted matrix cells remain pending until executed. The native iOS worktree, sources, caches and processes are outside this lane and untouched.

Phase 0 documents at commit `58a2a9d` and its [snapshot](evidence/phase1/phase0-snapshot.json) preserve prior commit denial and unauthorized state; those historical facts do not block approved Phase 1. No public operation, external message or hardware/actuator command was performed.
