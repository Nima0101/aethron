# Execution ledger

Current authority: [LATEST-OWNER-AUTONOMY](LATEST-OWNER-AUTONOMY.md), adopted after Phase 1 completion. Software P2–P5 and routine gate-dependent publication are authorized. Historical entries below retain the earlier scope.

## Historical Phase 1

Plan: IMPLEMENTATION-BACKLOG.md. Start: 1445f1879d63eb37f4bf8c367e53db74a95b1fe6. Owner authorization is recorded in PHASE1-START-AUTHORIZATION.md. No publication or Phase 2 authorization.

Pre-flight shared interfaces: P1.1 replay → P1.2 closed report; P1.2 frame types → P1.3 production workers; P1.3 supervisor-owned pipeline → P1.4 observation service; P1.4 envelopes → P1.5 expiring clients; P1.6 installed artifacts → P1.7 boot service. No ownership conflict: viewers never own capture.

Ruling: keep this durable task ledger instead of skill scratch automation, whose plan format differs and which can change shared Git excludes. Same RED/GREEN and per-task evidence obligations apply. Cost: manual ledger upkeep.
Ruling: self-review only because owner prohibits subagents; independent review remains pending.
Ruling: current GPL-3.0-only metadata supersedes earlier Apache references; frozen third-party licenses remain intact.

P1.1 RED: installed consumer fails building nonexistent integrations/edge. Full local output build/ecosystem-phase1/p11-red.log. No product completion claimed.

P1.1 GREEN: installed consumer 1/1, 24 frames with final depth/lwir/radar. Core wheel built twice byte-identically and external consumer passed. Plan validation 14 negative probes passed.
Ruling: redact only the owner approval’s absolute private worktree path to satisfy existing public-leak gate; original approval remains in commit 1445f18 and original digest is retained. Authorization meaning unchanged; cost is requiring Git history for verbatim original.

P1.1 committed 947b72d. P1.2 RED missing contracts/OpenAPI; GREEN 4 strict contract tests, 1 schema/export test, installed consumer 1/1 (62.179s). Full resolved dependencies audited before installation; no known vulnerabilities.

P1.2 committed e5335ec. P1.3 implements isolated file/UVC/RTSP and clocks/calibration. GREEN: source 4, clock 4, actual detector pipeline 2, real local RTSP 1. Initial timeout/closed-queue/RTSP failures retained in p13 evidence; hardware compatibility unqualified. Remaining resource/adversarial checks continue.
Ruling: generic OpenCV timestamps cannot be qualified exposure timestamps; those real pixel paths execute inference but withdraw current evidence. Cost: no current safety detections through these generic drivers until a qualified capture clock adapter exists.
Ruling: native virtualization reports unavailable; use QEMU TCG inside an isolated local tool container to boot a separate Linux guest. This is emulated Linux, not native ARM hardware performance.

P1.3 checkpoint 2739360. P1.4 GREEN: real process HTTP/SSE 4, security 2; lifecycle 3 and signed updates 3 implemented early to verify supervisor startup integrity. RED regressions fixed: malformed bearer, configured startup recommendation, worker cleanup blocking watchdog. Appliance boot/soak qualification still pending.

P1.4 checkpoint f4db8ce. P1.5 RED missing client module and TypeScript build; GREEN Python 2, TypeScript 2; real fresh installed server and external Python SSE client received 3 events, zero-viewer processing continued, both wheels reproducible.
P1.6 inherited visual mismatch reproduced, PNG delta confined to (26,27)-(478,51); rebuilt derived perception media only. Original/model/data/official-logo freezes unchanged; retained visual-repair.json and Phase 0 negative evidence.
Ruling: repository verifier now covers integrations/packaging/contracts and excludes generated npm/build trees; original failure was a third-party README link in ignored node_modules. Project leak checks remain active.
P1.7 first emulated Linux boot/reboot succeeded; initial soak probe failed at missing guest pgrep. Replaced with /proc enumeration; negative serial retained. Revised signed guest is now running a fresh full boot/soak.

P1.5 checkpoint 04f6dec. P1.7 VM exposed SIGKILL/Queue partial-message stall at 120s: count stuck at 1371. Kept negative evidence, replaced multiprocessing Queue with bounded shared-memory mailbox; killed-writer regression and lifecycle tests pass. Full emulated boot/soak restarted for this code. No stale result is represented as current.

Further P1.7 failure: mailbox removed partial-message risk, but killed Event.wait participant could still block Event.set during cleanup. A separate counterexample reproduces this; replaced interprocess stop events with one-way shared-byte polling tokens. The VM must pass fresh recovery before acceptance.

P1.6/P1.7 regression review: retained fresh core step results only until their existing expiry; calling core.watchdog on every GET had immediately withdrawn valid observations. Installed Node package now receives three SSE observations and still reports current UNKNOWN without a qualified transit clock. Calibration admission now rejects transforms not applied by the adapter (identity registered coordinates only); RED preserved in calibration-red.log.
Full integration run: 38 tests, one source negotiation failure. Other 37 passed including actual pixels, RTSP, installed consumers and update faults. Keeping the failure and investigating decoder metadata before candidate acceptance.

Candidate regression results: 46-test integration suite passed (173.375s). Prior failures remain in local logs and the negative-checkpoint ledger. Fixed test races with explicit synchronization; functional startup waits are distinct from frozen 100ms freshness. Decoder startup is bounded at 30s; pixel worker recovery at 60s; stale results still expire at 100ms. A previous 40s cold inference test failed under contention; this is retained, not a performance pass.
Installed final source paths: file + RTSP each ran pinned inference and delivered 3 external Python SSE observations, current UNKNOWN because exposure clocks remain unqualified. Cold time-to-inference-observation was 37.450s / 15.907s respectively (includes installation-independent startup/client work, not a camera-latency guarantee). Packed TypeScript client received 3 events. Linux arm64 and emulated amd64 installed container HTTP/SSE tests passed with no network, read-only root, dropped capabilities and zero-viewer processing.
Worker-tree review found abrupt inference death could strand a decoder. Added worker-owned POSIX group cleanup with exact registered-child fallback for sandbox restrictions, parent-owned decoder semaphore and Windows kill-on-close job code. Mac crash regression and three pipeline tests pass; Windows native execution remains pending. Source: S65/S66. An initial group signal was denied by the sandbox; no unrelated process enumeration or signals were used.
Offline update now connects signed inactive-slot selection to service startup. A Linux container actually staged version 2, rejected rollback, execed the verified slot as the dedicated account and processed offline. Final signed VM additionally runs this transaction with independent status sampling; the earlier blocking probe/update attempt is retained as incomplete. Test-only keys remain outside Git and are never copied into guest layers.

Committed candidate implementation at c7c6c2d with noreply identity; preserved the owner-authored untracked autonomy note without staging or adopting broader scope. Clean local clones of this commit passed installed edge/wheel consumers and existing source/zipapp/README quickstart reproduction. Core frozen benchmark p95 13.587ms/max25.602ms in this run; recorded AOT still 0TP/20FN/721 temporal FP. Earlier latency tails and negative evidence remain.
Final update permission review reproduced service-account replacement of a root-owned child under a writable parent. Moved the appliance update store beneath root-owned /var/lib, outside service write paths. Native Linux denied replacement and still execed/processed version 2. The protected-store VM now runs the fresh full gate; previous superseded VM artifacts/traces remain retained. No engine, model, data, logo, pricing or legal terms changed.

A06 measurement review found missing exported drop totals. A failing mailbox test reproduced the missing counters; implemented capture sequence-gap, mailbox-overwrite and busy-rejection counters with preservation across supervised worker restart. The guest probe accumulates observed deltas across the signed service update. Its previous protected-store run is retained as incomplete, not counted as the final hour. A fresh instrumented candidate must pass the whole gate.

The instrumented guest's first 45-second cold-boot window ended with only three status samples and no processed-frame increase under concurrent build load; its processing gate correctly failed. Retained the full trace and changed the first-boot observation window to 120 seconds. This is a functional cold-start bound, not a relaxation of 100ms evidence freshness or the required one-hour second boot. Runtime wheel is unchanged; image/probe evidence must be regenerated.

Candidate runtime committed at d90ae95. Full integration 48/48 passed in 101.578s; installed wheels are byte-identical with edge digest 49fda684…621d905. Updated Linux ARM64/AMD64 containers passed. Clean clones of d90ae95 passed both edge consumers and existing quickstart/source/zipapp reproduction. The installed pixel client's 20-second timeout failed once under concurrent load, then the unchanged focused run passed file/RTSP with actual inference and three events each (33.583s/15.382s cold observation times). The failure remains recorded, not erased or reclassified as a pass.

The final runtime's separate native Linux offline-update check passed signed version-2 exec, interrupted-stage preservation, rollback rejection and service-account update-store replacement denial. It emitted one shutdown semaphore warning; retained in offline-update.json. The real guest also completed its update transaction and continues the full hour gate.

Final signed guest passed: first boot 120.33s with processing, actual reboot, second boot 3,600.66s, worker crash/recovery before update, signed version-2 activation/exec, rollback rejection and clean test poweroff. Runtime/image template/wheel hashes match d90ae95 and the reproducible installed candidate. The actual second boot ran 3,600.66 seconds. Sampled synthetic processing latency: p50 8.513ms, p95 14.057ms, p99 17.034ms, max 87.603ms. Observed service cgroup peak: 123,715,584 bytes (about 118MiB); status record at most 347 bytes; journal 1,048,576 bytes. The report retains 89 mailbox overwrites, 208 busy-write rejections and 72 expired status samples; no uninterrupted-availability or zero-drop claim is made. Capture gaps are inapplicable to the synthetic source, and abrupt death can lose unpublished diagnostic increments. Phase 1 is recorded complete as software only; no publication, hardware qualification or Phase 2 advancement.

## Autonomous P2 checkpoint — 2026-10-08

Authority migration RED: previous validator rejected schema/current-phase change. GREEN: schema 3 retains Phase 1 completion snapshot and original approval hashes, binds latest directive, and adds tampered/missing authority, hardware/actuation escalation and unverified-publication counterexamples (23 total). No old failure was removed.

P2.1a packet RED: six missing-module assertions. GREEN: six raw raster/cloud/geometry tests. P2.1b replay RED: five missing-module assertions. GREEN: five bounded corruption/clock/source tests. Adversarial RED additionally exposed giant-int geometry overflow, malformed points and unacknowledged calibration changes; fixes use explicit validation and recording discontinuity, with 13 sensor tests passing. The full integration/package results are recorded separately in P2 evidence.

Ruling: raw sensor APIs live in the existing separately installed `aethron_edge.sensors` package; the backlog's proposed separate modality directory trees would duplicate transport/validation at this stage. Scope is retained. No semantic class or live-evidence promotion is inferred from raw packets. Real vendor SDK/ROS integration and nonvisible models remain next work.

Read-only GitHub checks: main remains 46e8828151ce17a7342d7dba6ce72963f540bc7b; authenticated repository access is available. Classic protection reports not protected and rulesets list is empty. Workflows enumerated; hosted CI and Pages/publication remain pending. No push/merge/deploy executed in this checkpoint.

Required fuzz: legacy 43,021 cases / 60.709s and temporal 172,683 cases / 60.302s, zero unexpected exceptions. Sensor replay corruption test additionally executes 2,000 deterministic mutations. Bandit sensor scope: zero findings. The first full integration run failed its existing 8-second zero-viewer startup assertion during concurrent builds (61 tests, one failure); the exact test passed unchanged in isolation (5.703s). Keep this as unresolved load sensitivity rather than claiming proven causation or changing the assertion. Sequential full-suite and fresh wheel checks follow.

Sequential final GREEN: 62 integration tests / 240.478s; installed sensor tests 14/14 outside checkout; authenticated HTTP/SSE consumer and zero-viewer processing pass. Two builds produce identical edge wheel `6dca68d35f870aefb2ec970e92cf044212751a75a1e867010b1541c17abbaef4`; core wheel remains `be3dd8e3e8bcf437d72d65e384c560eb18d4b22baf522849b965d3d720c1d73f`. P2.1 remains partial. Committed clean-clone reproduction follows this source checkpoint.
