# Current handoff — autonomous P2 implementation

The later [owner autonomy directive](LATEST-OWNER-AUTONOMY.md) is now adopted. Continue software milestones and gate-dependent routine publication without repeated approval. [NEXT](NEXT.md) gives the next executable task; [sensor progress](P2-SENSOR-ADAPTERS.md) describes this checkpoint. P2.1 is partial, not complete; no hardware, semantic nonvisible model or hosted publication claim has been added.

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
