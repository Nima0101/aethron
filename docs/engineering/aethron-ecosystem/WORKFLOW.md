# Contributor workflow and phase discipline

## Phase 0 workflow that exists

Only this planning directory, `scripts/check_ecosystem_plan.py` and the dedicated preflight workflow are Phase 0 source additions. The checker uses the standard library, validates required artifacts, strict JSON structure/state, relative links and fragments, source/pin provenance and protected baseline hashes, and runs real negative mutation tests with `--self-test`. Run from root:

```sh
python3 scripts/check_ecosystem_plan.py --self-test
python3 scripts/verify.py
```

The preflight has no product smoke test masquerading as integration evidence. It has no publication credentials, model download, hardware access or workflow edits outside its own file. See [HANDOFF](HANDOFF.md) for actual local outcomes, including baseline failures.

## Authorized implementation session

1. Read AGENTS and frozen documents, START_HERE/STATE/NEXT. Confirm exact intended worktree, branch, clean/known working changes and owner START. Do not alter any other worktree or native iOS cache. Work without subagents.
2. Read the task's contract and evidence gate. Make a failing behavior test for meaningful new logic; keep malformed bytes/negative clips as fixtures without private data. Commit scope is one independently reviewable behavior.
3. Implement the actual adapter/service/package/client path, not an inert mock. Use fake devices or licensed recordings to cover unavailable hardware, clearly labeled, alongside production driver code.
4. Run focused checks, then required repository verification and relevant E2E/packaging/security gates. A failure remains a failure; record output/hash and cause if known. Run performance checks in an otherwise quiet session where possible, but retain noisy failures and do not stop others' processes.
5. Review diff for source scope, frozen files, new credentials/identity data, unsupported claims and licensing. Generated artifacts must come from actual commands and carry source/model/data digests.
6. Update STATE/NEXT/evidence/task checkboxes truthfully. Make cohesive local commits with a verified public noreply identity. Never expose private git identity in logs/docs.
7. At a phase boundary, deliver concrete artifacts, checks and unresolved blockers. Stop until the owner authorizes the next phase. Publishing is a separate action requiring all publication prerequisites and explicit owner authorization.

## Branch/PR and integration lifecycle — future authorized use

Create an issue/task acceptance record and a scoped feature branch. A PR description leads with changed behavior, validation and limitations, links versioned decisions, and identifies exact-source evidence. Review public contract changes against conformance fixtures; preserve historical thresholds. Native iOS integration is a later owner-mediated handoff of contract/fixtures, not edits in another agent's source tree. Resolve integration conflicts only within the assigned worktree after ownership is clear.

No PR/push is authorized by Phase 0. Later PR/merge checks must use actual hosted run URLs and immutable artifacts, not status copied from this local session. A release issue ties user-facing support claims to [TEST-EVIDENCE](TEST-EVIDENCE.md) levels and specific device tuples.

## Maintenance and observability specification

Process health, source frame age/drop count, calibration expiry, provider startup/faults, inference latency histograms, RSS and version digests are useful aggregate metrics. Avoid raw frames, boxes, person/track IDs, exact routes or stable user/device identifiers in metrics by default. Keep session state in memory and purge on expiry/close. Health endpoint does not mean valid perception.

Proposed maintenance cadence: monthly upstream/security/license review, release-specific compatibility recheck, reproducible lock refresh with regression evidence, and incident-triggered update/hazard review. Roll back atomically to the previous verified environment when migration fails; never roll back to a known vulnerable or contract-incompatible build without a reviewed recovery decision. Establish support contacts/SLOs only when maintainers can actually fulfill them.

## Status transition after this delivery

The current checker deliberately enforces the delivered Phase 0 state, including its unresolved local-commit limitation. Resolving that limitation or approving Phase 1 requires an explicit reviewed status/schema/checker transition in one change, with actual evidence/owner authorization. Do not weaken the phase flags merely to obtain a green future build. Baseline governance/data/model protection remains mandatory independently of phase state.

## Appliance-first development acceptance

Every Phase 1 design/test starts with supervisor-owned pipelines and no required viewer/backend. P1.7 executes the post-provision unplug/reboot/offline harness on an actual service-manager VM; calling a Python function is not a boot test. Installer/CLI/UI are maintenance tools and cannot become hidden runtime dependencies. Required failure tests cover restart budgets, independent freshness, local notifier, disk-full, integrity and update rollback. Each deployment class receives a normal-user power/status/recovery guide and a technician guide; test both against an installed image. No host system service is installed in this Phase 0 session.
