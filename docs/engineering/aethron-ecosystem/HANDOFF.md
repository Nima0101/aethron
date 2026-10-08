# Phase 0 handoff

Prepared on branch `feat/aethron-vehicle-uav-preparation-20261008` from `59fda946771d4ac8c9d1b52eeb3d948215325e4c`. Current HEAD remains `59fda946771d4ac8c9d1b52eeb3d948215325e4c`: staging/commit was blocked when the sandbox refused the linked worktree index lock. All deliverables remain uncommitted in the assigned worktree. No escalation was available or attempted; no other worktree was changed. No push, merge, public release, deployment, external message, hardware operation or Phase 1 product implementation occurred.

Delivered: the navigable [START_HERE](START_HERE.md), baseline/state/phase records, 64-entry primary-source ledger with version/provenance records, architecture/API/packaging specification, generic vehicle recipes and Mazda case study, open/commercial drone integration pathways, true-zero-visible sensing/calibration plan, threat/assurance/evidence matrices, contributor/release workflow and file-level phased backlog. The standalone [Phase 1 prompt](PHASE1-EXECUTION-PROMPT.md) is gated on owner START. Native iOS source and its owner remain untouched.

The only executable source additions are the standard-library planning checker and its dedicated read-only GitHub Actions workflow. They validate documents, JSON/state/dependencies, citations, version pins, relative links/anchors and protected hashes, including negative mutation tests. They do not qualify the product or run hosted until actually published/executed.

Actual baseline checks and limitations are in [BASELINE](BASELINE.md) and [checks.json](evidence/checks.json). The inherited visual reproduction failure is preserved. Final clean-clone and isolated-plan evidence is appended below. The local commit requirement remains unfulfilled.

Known unknowns: exact OEM camera access and vehicle trim/market; vendor SDK/device/firmware tuples and redistribution rights; thermal dataset terms and held-out model performance; physical clock/calibration/power/thermal/range evidence; representative zero-visible and field results; external safety/privacy/cyber review; required hosted platform runs. None prevents future adapter/software work after authorization. None is represented as production approval.

**Next authorization:** the owner may say “START Phase 1” to run the supplied execution prompt. Until then, stop. Research and planning checks do not authorize automatic phase advance or publication.

## Local commit blocker and safe completion command

The failed action was `git add` of only the new planning directory/checker/workflow. Git's linked-worktree index lives outside this sandbox's writable roots; creating `index.lock` returned `Operation not permitted`. This was a filesystem sandbox denial, not an automatic content-review rejection. No commit was created and nothing was pushed. A public GitHub noreply identity was verified from existing repository history without publishing private identity.

In a terminal/session permitted to write this worktree's Git administration, the owner can review and commit these exact files:

```sh
python3 scripts/check_ecosystem_plan.py --self-test
git add docs/engineering/aethron-ecosystem scripts/check_ecosystem_plan.py .github/workflows/aethron-ecosystem-preflight.yml
git diff --cached --check
git -c user.name=Nima0101 -c user.email=118866572+Nima0101@users.noreply.github.com commit -m "docs: prepare AETHRON ecosystem Phase 0 blueprint and preflight"
```

These commands do not push or start Phase 1. After an actual successful commit, record that result in a follow-up status amendment and update the checker's Phase 0 commit-state expectation together; do not mark it committed based only on these instructions. The current blocked-state check deliberately preserves the truth of this delivery.

## Owner-added standalone runtime extension

Preserved the owner-authored requirement and incorporated it into architecture/API lifecycle, packaging, vehicle/Mazda/drone recipes, a new home camera/NVR guide, workflow/CI/threat/evidence plans and the standalone execution prompt. Added APPLIANCE-RUNTIME with exact supervisor/boot/update/recovery requirements, A01–A09 gates and required P1.7 implementation tasks. The normal installation runs independently of a provisioning laptop/phone, API client, WAN or backend; all remains SPEC ONLY. No native mobile files or host services were changed.

## Final local verification

- Planning preflight: 64 primary-source records; 12 mutation/rejection tests, including appliance independence and mandatory A01–A09 gates. Ruff check/format and local YAML structure checks pass. Synthetic API example is accepted by the actual frozen parser/runtime.
- Repository verification: 66 tests and required static/frozen/data/consumer/temporal CLI checks pass locally. Both 60-second fuzzers pass; Bandit has zero findings in runtime Python and the existing 41-package development dependency audit reports zero known vulnerabilities as checked on the research date.
- Isolated wheel: reproducible builds and installed consumer pass. Clean clone of committed baseline `59fda94` passes quickstart/frozen temporal evaluation, external zipapp consumer and two identical source/release builds; it excludes uncommitted planning files. See [clean-clone evidence](evidence/baseline-clean-clone.json).
- Visual reproduction **fails** against baseline PNG/GIF artifacts; original input/output JSON and HTML match. Retained title-region evidence and P1.6 repair task make this an explicit publication blocker.
- Hosted CI, installed appliance image/auto-boot, exact sensors/vehicles/drones, physical zero-light and external qualification are not executed or claimed. P1.7/A01–A09 are planned requirements only.

All product source, frozen evidence and corrected branding assets remain unchanged. Full Phase 0 acceptance is blocked only by the requested local commit; product qualification additionally retains all documented inherited/physical gates. All created planning files remain available in the assigned worktree.

The final isolated-copy check also passed: the baseline was cloned locally, the 45 planning/checker/workflow files were copied explicitly, and both preflight and repository verification exited zero. [Overlay manifest and results](evidence/isolated-plan.json) bind the exact checked files; this is not presented as a committed candidate. Subsequent handoff/evidence bookkeeping is validated by the final local preflight.
