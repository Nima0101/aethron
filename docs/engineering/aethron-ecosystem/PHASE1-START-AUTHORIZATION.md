# AETHRON Phase 1 — owner start authorization (2026-10-08)

**Status: START AUTHORIZED.** On 2026-10-08 the owner explicitly stated, in Swedish: "Okej bra, nu astra high är även klar med sin planering och allt och ska nu starta igång sitt arbete." This follows the earlier owner's explicit direction to complete planning first, then seek approval before implementation.

Authorization is **limited to Phase 1 (P1.1–P1.7)** as prepared in [the execution prompt](PHASE1-EXECUTION-PROMPT.md), [implementation backlog](IMPLEMENTATION-BACKLOG.md) and [appliance-runtime requirements](APPLIANCE-RUNTIME.md). Start product implementation now; do not treat the Phase 0 historical `phase1_authorized: false` snapshot as newer than this express approval. Update current state documents/checker appropriately with auditable truth, preserving Phase 0 evidence.

## Execution boundary

- **Codex model:** GPT-6 Astra, High. Resume existing planning thread `01a11b35-29c0-74e2-ba67-21074d0dcb28`; no subagents.
- **Assigned branch/worktree:** `feat/aethron-vehicle-uav-preparation-20261008` in `<owner-assigned-parent>/aethron-vehicle-uav-preparation-20261008`.
- Phase 0 was actually committed at `58a2a9d` and integrated with public main `46e8828` in local merge `8d0da0e`. Preserve the updated **GPL-3.0-only / separate commercial licensing** documents and public pricing page. Those files are already present in this branch.
- The unrelated native iOS Codex session remains active in a separate worktree. Never modify, stop, send messages to or rewrite its Swift/Xcode files, PID, logs, branches, caches or runtime. No common output directories.
- No merge, remote push, public release, online deployment, third-party paid subscription, hardware control, vehicle actuation or UAV command is authorized. No phase 2–5 automatic advancement.
- Source changes require genuine implementation, actual tests, software-in-loop offline deployment/boot evidence and visible unsupported hardware status; no fake production, certification or zero-light field claims.
- Local Git commits to **this feature branch only** are authorized, with verified GitHub noreply identity.
- An authorized external Mac session resolved Phase 0's Git index-lock issue; future worker may need Git common metadata writability to commit. Do not interpret a sandbox block as an engineering failure. If a Git commit is still denied, keep implementation and checkpoint details intact without altering another worktree.
- Use the latest exact owner requirement: after one-time provisioning AETHRON boots unattended with permanently integrated sensors/compute/power, live local processing with no mandatory laptop/phone tether, user USB provisioning connection, internet, Supabase/Coolify or licence-server heartbeat.
- Do not claim a computer, powered hardware, sensor or data cable is magically unnecessary; the deployment is an integrated standalone appliance. The physical no-light detection claim requires real non-RGB modalities and measured hardware evidence.

## Deliverable

Execute P1.1–P1.7 as real code and reproducible evidence. Report each actual integration capability separately from physical/field qualification. Stop at the end of Phase 1, with status/next and Git checkpoints; the owner will decide the next phase.
