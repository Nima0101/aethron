# Phase 1 execution ledger

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
