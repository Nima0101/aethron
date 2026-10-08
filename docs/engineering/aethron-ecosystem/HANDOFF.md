# Latest continuation checkpoint — recorded sensor appliance

Implemented [signed raw replay supervision](SENSOR-APPLIANCE.md), configuration/integrity binding, bounded worker, parent expiry and recovery, local diagnostics, real authenticated HTTP/SSE and a synthetic example. [Current state](STATE.md) and [evidence](evidence/phase2/sensor-appliance.json) distinguish executed checks from pending gates. Full Mac installed packaging remains failed/pending after startup/OpenCV timeouts; Linux installed raw/DDS and Mac source/raw/API component checks passed. Do not publish or claim new VM boot/physical qualification.

Next executable task: diagnose installed Mac startup/rectification timing using `build/ecosystem-phase2/sensor-appliance/diagnostic-venv`, complete committed clean reproduction, then ROS per-boot authority/supervisor wiring. This is a continuation checkpoint, not an approval stop. Current worktree HEAD is reported by `git rev-parse HEAD`; historical source `58addca` remains the last fully reproduced checkpoint below.

## Earlier provider checkpoint — historical

Verified source: `58addca8182d6b77749c105e1bf9dc4b9a346093`. [Provider implementation](SENSOR-PROVIDER.md) now connects calibrated raw depth replay and ROS depth/cloud geometry, with clock/source/mount/format/calibration withdrawal and actual installed DDS consumption. [Clean reproduction](evidence/phase2/provider-clean.json) passed identical source/ZIP artifacts, isolated consumers, 49 installed sensor tests, seven OpenCV tests, HTTP/SSE and zero-viewer continuation. The frozen temporal benchmark passed at p95 13.633ms/max73.689ms. Source verification passed 107 integration tests, 75 core tests, 54 installed ROS tests, security/lint, 26 plan negatives and both required fuzz runs. Exact wheels and retained counterexamples are in [provider evidence](evidence/phase2/provider.json).

Next: provisioned provider configuration and bounded appliance worker/supervisor integration. No public operation or physical qualification is claimed.

Earlier checkpoints below retain their original scope and results.

Latest verified source: `ce5294d924ccb6bff52cc56cba4b6df017c99e16`. [Clean reproduction](evidence/phase2/resource-clean.json) passed source/ZIP artifacts, isolated consumers, 39 installed sensor tests, six OpenCV rectification tests, HTTP/SSE and zero-viewer continuation. The frozen temporal gate passed at p95 9.225ms. Core wheel `726e4079ed72437958010e0af944d2a85dfab8ce531ba90c35903cf92cf7e04e`; edge wheel `8fddc0557864a1b0b511812cddd12f364a708147d954e148d4a9822842c4ac74`. Actual wheel ZIP import also passed on local Python 3.9.6. Browser sandbox permission, native Windows hosted confirmation and other publication prerequisites remain pending. No public push occurred. Next executable coding task is calibrated raw-sensor provider admission/connection; P2/P3 and hardware qualification remain incomplete.


The later [owner autonomy directive](LATEST-OWNER-AUTONOMY.md) is now adopted. Continue software milestones and gate-dependent routine publication without repeated approval. [NEXT](NEXT.md) gives the next executable task; [sensor progress](P2-SENSOR-ADAPTERS.md) describes this checkpoint. P2.1 is partial, not complete; no hardware, semantic nonvisible model or hosted publication claim has been added.

Latest local release-preparation evidence is [recorded here](evidence/phase2/publication-preflight.json), with [clean geometry reproduction](evidence/phase2/registration-clean.json). Resource-loader and candidate-SBOM fixes are software changes; browser permission and native Windows hosted confirmation remain open gates. Continue the calibrated provider task without waiting for hardware or another phase approval.

The remainder is the historical Phase 1 handoff at `f40fbd1`; its stop/authorization language describes that earlier checkpoint, not current authority. Its tests, hashes and failures remain historical evidence.

## Historical Phase 1 handoff — software candidate complete

Phase 1 is authorized. P1.1–P1.7 passed their software-candidate gates, including the real 3,600.66-second second-boot soak. The [acceptance record](evidence/phase1/acceptance.json) binds the exact source and artifacts. No push, merge, public release, deployment, hardware actuation or Phase 2 work occurred.

Branch: `feat/aethron-vehicle-uav-preparation-20261008`. Reviewed runtime source: `d90ae953f6431fd9d460e440432ac72825b8d250`. Evidence checkpoint before final acceptance: `5f670d2`; final bookkeeping follows it on this branch. Historical Phase 0 `58a2a9d`, public-main integration `8d0da0e` and owner approval `1445f18` remain intact. The owner-authored untracked autonomy note is preserved separately and does not expand this session's explicit scope.

| Milestone | Delivered and checked | Current gate |
|---|---|---|
| P1.1 | Installable separate edge wheel, CLI/import, external installed replay/service consumers | Passed |
| P1.2 | Closed typed schemas, strict byte admission, canonical OpenAPI and actual core fixtures | Passed |
| P1.3 | Real file/UVC/RTSP workers, clock/calibration, pinned pixel inference/registration/replay, loss handling | Passed software; physical UVC/OEM unqualified |
| P1.4 | Authenticated local HTTP/SSE, bounded sessions/events, independent supervisor and freshness | Passed |
| P1.5 | Installed Python and packed TypeScript/Node consumers, local expiry, native fixture handoff | Passed; browser/native integration pending |
| P1.6 | Reproducible wheels, Linux ARM64/AMD64 containers, clean clone, SBOM/audit/fuzz/visuals, dedicated CI | Passed on executed matrix; hosted/native pending cells explicit |
| P1.7 | Signed systemd image, boot/reboot, no NIC/login/viewer, crash recovery, offline version-2 update, local status | Passed real boot/reboot and one-hour software soak |

Use [edge installation](../../usage-edge.md) for exact package/API commands and [appliance operation](../../usage-appliance.md) for one-time installation and normal automatic boot. The normal Linux appliance supervisor owns processing; a terminal, phone, laptop, provisioning host, WAN, cloud account or licensing heartbeat is not a guest runtime dependency. Permanent physical compute, sensors, mounting and power remain necessary. A Docker-hosted QEMU guest proves the software lifecycle, not an installed physical appliance.

Validation: 48 integration tests passed in 101.578s, plus the strengthened artifact measurement gate; two TypeScript tests; installed Python/Node HTTP/SSE consumers; real licensed file/RTSP inference; two byte-identical wheel builds; Linux ARM64 and emulated AMD64 container consumers; clean-clone edge/core/README/source/zipapp reproduction; repository verification and 18 plan-negative probes; both required ≥60-second fuzzers; SBOM schema/audit/security review and byte-identical visual reproduction. See [test evidence](TEST-EVIDENCE.md), [review](REVIEW.md), [appliance gate mapping](APPLIANCE-EVIDENCE.md) and [execution ledger](EXECUTION.md).

The edge wheel SHA-256 is `49fda684a90da9667ff1717ece3a9a3b631b33fda43a72ea952ce129f621d905`; core wheel is `be3dd8e3e8bcf437d72d65e384c560eb18d4b22baf522849b965d3d720c1d73f`. The signed guest and clean-clone consumer use those exact bytes. Models, datasets, official corrected logo, GPLv3-only/separate-commercial terms, pricing and buyer/legal material were preserved.

Limits: generic OpenCV exposure timestamps are unqualified, so those live paths emit UNKNOWN current evidence. The boot source is synthetic multimodal proposals; actual RGB pixels are tested separately. Physical zero-visible sensing, OEM access, camera SKUs, power/thermal behavior, field safety and certification are unqualified. Windows/macOS Intel, native mobile/browser integration and hosted CI are not represented as executed. The recorded aircraft evaluation still has 20 misses and 721 temporal false positives. Earlier latency failures, an installed-client timeout under load, cold-start failure and shutdown semaphore warning remain documented; no hard-real-time or zero-leak claim is made.

Phase 1 stops here for owner review. No pending hardware or native/hosted qualification is represented as complete. Future hardware qualification and P2–P5 require their own authorization; this handoff does not launch them.

The actual second boot ran 3,600.66 seconds. Sampled synthetic processing latency: p50 8.513ms, p95 14.057ms, p99 17.034ms, max 87.603ms. Observed service cgroup peak: 123,715,584 bytes (about 118MiB); status record at most 347 bytes; journal 1,048,576 bytes. The report retains 89 mailbox overwrites, 208 busy-write rejections and 72 expired status samples; no uninterrupted-availability or zero-drop claim is made. Capture gaps are inapplicable to the synthetic source, and abrupt death can lose unpublished diagnostic increments.

The final checked Git HEAD is reported with the session handoff; `git rev-parse HEAD` resolves the local bookkeeping commit without a self-referential hash in this file. Runtime source remains the immutable d90ae95 revision above.


Current P2 source checkpoint: `dd2328ee398b3d8177635914644a3ba326ab5386`. Clean-clone governance/plan checks, installed sensor/HTTP/SSE consumers and byte-identical wheels passed. Source archive and zipapp also reproduced, but **overall reproduction failed its frozen Mac latency gate**: p95 118.711ms, then unchanged synthetic retry 129.476ms, against 100ms. A separate offline Linux ARM container running identical core/evaluator bytes passed at p95 1.501ms. All outcomes, CPU timings, source hashes and the original aircraft failures are retained in [performance evidence](evidence/phase2/performance.json). Linux success does not replace the native Mac failures. Publication remains held; independent software implementation continues. Hardware/field qualification remains pending.


Current ROS checkpoint adds the optional installed Jazzy Image/CameraInfo/PointCloud2 subscriber, bounded message admission, explicit expiring clock mapping, calibration withdrawal, source-loss handling and headless status/shutdown. It is partial P2.1/P3.1; the signed appliance source/model-provider integration and physical qualification remain pending. [ROS evidence](evidence/phase2/ros2.json) binds the exact executed SDK tuple, wheel hashes, tests and retained failures. The new ARM64 CI workflow has not run remotely. Latest source commit is resolved by `git rev-parse HEAD`; no public operation occurred. Continue with the concrete coding task in [NEXT](NEXT.md), without an approval stop.

New ROS-checkpoint verification: the unchanged native temporal gate passed at p95 9.610ms (CPU diagnostic p95 9.070ms); earlier failures are retained rather than overwritten. The 76-test full integration run had one eight-second startup failure; its unchanged isolated retry passed in 1.364s. The fresh sequential full run passed 76/76 in 77.111s; committed-source reproduction follows this checkpoint. Publication has not occurred.

Committed ROS source `bc2ffe4b6fca49e90d265ea5cffc8bea2485647d` passed clean-clone core/quickstart/zipapp/source reproduction and the full frozen evaluation (native p95 11.679ms). [Current reproduction](evidence/phase2/ros-clean.json) supplements, never replaces, the historical latency/aircraft failures. Routine publication is authorized after the remaining publication prerequisites and hosted CI; no new owner START is needed.

Clean-clone edge installation also passed on that revision: identical core/edge wheel hashes, 28 installed sensor tests, three authenticated SSE events and continued processing after disconnect. Final required fuzz runs: 93,127 legacy cases/60.001s and 247,724 temporal cases/60.236s, zero unexpected exceptions. Local build-space reservation was released; no other-session cache was cleaned.

Current geometry increment implements strict 3D-to-optical rigid registration, declared error footprints, expiring clock/mount bindings and optional sparse lens rectification/deprojection. The full integration suite passed 92 tests in 159.362s; installed matrix results are in [registration evidence](evidence/phase2/registration.json). This remains partial P2.1; no model, ROS CameraInfo promotion, appliance provider or physical qualification is inferred. [NEXT](NEXT.md) identifies the provider connection task.

The final broad Mac regression retained two availability failures (115 tests); eight focused worker tests pass after correcting raw duration reporting. Final installed Linux results and current artifact hashes are in [sensor-appliance evidence](evidence/phase2/sensor-appliance.json). Earlier Mac component results predate the duration diagnostic fix. Full current Mac and committed reproduction remain open.
