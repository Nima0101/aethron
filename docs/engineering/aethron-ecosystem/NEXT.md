> **Current supersession, 2026-10-08:** Phase 0 committed at `58a2a9d`; approved merge `8d0da0e`; [owner START](PHASE1-START-AUTHORIZATION.md) at `1445f18`. Phase 1 P1.1–P1.7 is now in progress. [Current machine state](PHASES.json) and [execution ledger](EXECUTION.md) supersede the historical Phase 0 text below. No push, deployment or Phase 2 is authorized. Project-owned code uses GPL-3.0-only with separate commercial licensing.

# Next — stop at the Phase 0 boundary


## Owner priority: standalone appliance runtime (mandatory plan extension)

Before considering Phase 0 genuinely prepared for owner review, fully integrate the owner's [permanent standalone runtime requirement](OWNER-NEXT-APPLIANCE-RUNTIME.md) in the ecosystem blueprint and planned implementation workflow. This is **the NEXT architecture requirement**, not an authorization to code features:

- Make **embedded/on-device, unattended auto-start and persistent offline inference** the normal consumer/fleet installation path. OEM-approved native compute is preferred; otherwise use permanently installed, appropriately powered edge/retrofit compute with compatible sensors. No external laptop, phone, developer USB tether, CLI login, internet, Supabase, Coolify or online licence heartbeat is needed after provisioning to run the local perception pipeline.
- A temporary setup tool is permitted. Prove with an **unplug/reboot/offline end-to-end acceptance test** that neither installer nor companion device remains necessary. Tests should include ignition/device power cycle, watchdog/recovery, model integrity, stale/zero-light sensor failures, thermal and latency limits, plus local independent alerts/API. Different vehicle/drone/home camera installation classes require their own concrete recipes.
- Define packaging/autostart targets and upgrade lifecycle: signed edge images or native packages, OS service manager, safe configuration, plugin/model manifests, local UI/status, debug and recovery, verified fallback. Sensor/compute/power remain physically integrated (not magically absent).
- Add explicit dependent tasks/gates to PHASES.json and IMPLEMENTATION-BACKLOG.md, mark each state correctly as SPEC ONLY, and update PACKAGING, VEHICLE-COMPATIBILITY, DRONE-COMPATIBILITY, WORKFLOW, ARCHITECTURE, TEST-EVIDENCE and PHASE1-EXECUTION-PROMPT. Explain non-negotiable OEM camera and iOS background restrictions without reducing ecosystem scope.
- Phase 0 remains **planning and workflow preparation only**. Do not start product implementation until the owner explicitly says START.


The remaining Phase 0 action is a local commit from a session/terminal permitted to write this worktree’s Git metadata. The current sandbox rejected staging; no escalation is available. After reviewing the concrete files and handoff, the next product action is **owner authorization to START Phase 1**. Do not invoke the execution prompt autonomously, create product scaffolding or treat a green preflight as authorization.

After authorization, the single implementer reads [PHASE1-EXECUTION-PROMPT](PHASE1-EXECUTION-PROMPT.md), verifies branch isolation, rechecks [BASELINE](BASELINE.md), and executes P1.1–P1.7 from [IMPLEMENTATION-BACKLOG](IMPLEMENTATION-BACKLOG.md). Phase 1 delivers a supervised auto-boot appliance candidate with unplug/reboot/offline software evidence, a locally installable integration package, strict byte-preserving v3 transport, replay/UVC/RTSP paths, bounded service/SSE and actual external sample clients. It does not claim all future sensors are supported.

Independent preparation in subsequent authorized phases: obtain dataset terms and exact sensor/vehicle inventory, collect legal operational-domain requirements, compare runtime/model candidates, and agree on conformance with the native iOS owner through the owner. Lack of hardware blocks SKU qualification, not software implementation.

Owner decisions needed at later gates: intended first deployment domain/jurisdiction, available device SKUs and power/mount constraints, dataset redistribution rights, and whether any bounded defensive controller integration is desired. None is required to complete this planning phase.

Publication remains disallowed until repository publication prerequisites pass and the owner separately authorizes it. No push, merge, release, deployment, email or hardware command is part of Phase 0.

The mandatory runtime extension is now concretely specified in [APPLIANCE-RUNTIME](APPLIANCE-RUNTIME.md) and [HOME-CAMERA-COMPATIBILITY](HOME-CAMERA-COMPATIBILITY.md), with P1.7/A01–A09 added to the dependent backlog and phase record. All remain SPEC ONLY until START; no permanent service/image exists yet.
