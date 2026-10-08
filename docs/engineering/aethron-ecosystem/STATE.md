# State — 2026-10-08

Phase 0: research, architecture and workflow preparation delivered; validation recorded in [HANDOFF](HANDOFF.md). The requested local commit is blocked by sandbox access to linked worktree Git metadata, so full Phase 0 acceptance is not marked complete. Phase 1: awaiting explicit owner START; no product features implemented by this phase. Hosted execution, publication, deployments and hardware operation: not performed.

## Baseline and claims

[BASELINE](BASELINE.md) binds inherited capabilities and fresh local checks to the starting SHA. The Python package/import/CLI, bounded v3 tracker, strict parser, synthetic multisensor adapters, YOLOX integration, optional Core ML and camera PWA already exist. A sensor-shaped JSON adapter is not a tested physical sensor driver. No general HTTP service, enterprise SDK suite, generic OEM video bridge or qualified automotive/UAS installation is established here.

The historical status file predates later branding/PWA publication; use its runtime evidence with its source SHA, and read its dated remediation. Do not repeat its old “no remote/live platform” statement as current global truth. The public URLs were inspected in Phase 0; deployment provenance and physical phone behavior were not independently qualified.

## Ownership lanes

| Lane | Accountable role | Boundary |
|---|---|---|
| Governance and phase authorization | Owner | Accept scope, approve phase starts and separately authorize publication |
| Core, transport, packaging, portable tests | Future Phase 1 single implementer | This feature branch/worktree only; no agents |
| Native iOS | Existing separate Swift/SwiftUI owner | Interface consumer; no edits/build/cache work here |
| Android and desktop clients | Later platform implementer | Conformance fixtures first, actual installation proof next |
| Vehicle and UAS adapters | Later integration implementer | Authorized sources, observe/assist before qualified control |
| Sensor/model evaluation | Dataset custodian and evaluator roles | Freeze partitions and metrics before tuning |
| Physical qualification | Device owner and competent test team | Exact hardware/firmware/environment and controlled trials |
| Independent assurance | External reviewer/certifier when applicable | Same-author review does not fill this role |

Roles are assignments to be made at the relevant phase, not claims of staffed teams. Parallel lanes describe dependency independence; this session uses no subagents.

## Cadence

Each work session begins with branch/status and authority checks. Each cohesive change records tests, failed attempts and evidence hashes. Each milestone updates PHASES and NEXT; owner reviews at phase boundaries. Compatibility/SDK terms must be rechecked at the beginning of implementation and before every release. Monthly maintenance triage is a proposed post-release cadence, not an operating service.

Progress flags and dependency order are authoritative in [PHASES.json](PHASES.json). Product milestones remain false even when planning preflight passes.

## Owner appliance extension

The owner-added permanent-runtime requirement is preserved verbatim and integrated into [APPLIANCE-RUNTIME](APPLIANCE-RUNTIME.md), all affected contracts/recipes, P1.7 and A01–A09. Plans prioritize auto-boot offline inference independent of optional clients. Implementation/measured appliance progress remains false; no host service/image/hardware was operated. The native iOS lane remains an optional client subject to OS lifecycle.
