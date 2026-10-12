# Hosted verification failure retention review

Baseline: `401452e6240027dffe9c04e79fc44e6338cac6fc`.
The P4/P15 review reached the remaining hosted scheduling configuration after the
Node result checks. Default matrix fail-fast could cancel the other supported
Python version. Default step success conditions skipped independent review,
report-reproduction, formatting, security and comparison checks after an earlier
failure. An always-running artifact upload does not execute skipped checks.

## Deployment constraints and technology decision

This component schedules finite synthetic checks on GitHub-hosted Ubuntu runners.
It must preserve failed job status, require successful preparation, respect
cancellation and retain the existing five-minute job limits. It has no hard
real-time deadline, device interface, credential service or product-runtime role.
Hosted CI is not a dependency of offline product operation.

| Candidate | Decisive property for this boundary |
|---|---|
| Native Actions YAML conditions and matrix controls | Direct access to runner cancellation and completed step outcomes, with separately visible failed checks. |
| Python subprocess coordinator | Can collect child exits and run independent commands, but still needs native matrix and cancellation configuration. It would move per-step outcomes behind another result aggregator. |
| F# asynchronous coordinator | Credible cancellation-aware orchestration outside the present component's language; its process/task cancellation does not replace the host's matrix and step admission rules. |
| Nix derivations | Relevant to declared build dependencies and reproducible inputs. They do not supply the required Actions cancellation/outcome policy. A hermetic-build requirement needs its own evidence. |

**KEEP native workflow configuration; FIX conditions and matrix fail-fast.**
The selection follows ownership of the scheduling state, not installed tooling,
familiarity or migration cost. No cross-runtime performance comparison is claimed.
Primary references inspected for this review:
[Actions matrix failures](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstrategyfail-fast),
[status expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions),
[step outcomes](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#steps-context),
[Python subprocesses](https://docs.python.org/3.13/library/subprocess.html),
[F# asynchronous expressions](https://learn.microsoft.com/en-us/dotnet/fsharp/language-reference/async-expressions),
and [Nix derivations](https://nix.dev/manual/nix/2.34/language/derivations.html).
The candidate comparison is engineering analysis. An attempted Nix CI tutorial
fetch failed; no suitability claim relies on that unavailable page.

## Corrected admission and remaining limits

The two Python matrix jobs now use `fail-fast: false`. Six contract checks require
successful Python preparation; formatting and security checks require successful
tool installation. Java transport checks require successful compilation and its
existing fingerprint checks. The later Node/hash/campaign experiments require
successful input/tool observations, so a failed Java comparison or compilation
does not automatically skip those independent experiments.

Each new condition includes `!cancelled()` and the prerequisite's `outcome ==
'success'`. Preparation steps retain their existing default success dependency
chain from checkout. Failed, skipped, cancelled or unavailable prerequisites do
not admit downstream checks. Explicit cancellation still stops admission. No
`continue-on-error` was introduced: a passing later check cannot turn an earlier
failed step into a passing job. Upload conditions and seven-day retention remain
unchanged.

Preparation is still shared. A failed checkout, tool setup, pinned parser download
or input-observation step can prevent multiple experiments. This correction does
not claim complete experiment isolation, guaranteed artifact delivery, protection
from job timeout or a failover runner. Commands within each step retain their
existing dependencies and shell failure behavior. Partial/missing artifacts are
incomplete diagnostic evidence, never release acceptance.

## Verification scope

The initial static configuration audit identified thirteen mismatches: one matrix
setting and twelve step conditions. The corrected inspection checks their explicit
prerequisites, unchanged timeouts, absence of error suppression and retained upload
conditions. Actionlint checks the actual YAML and expression references. These are
configuration checks against documented semantics, not a local Actions scheduler.

Nine unchanged workflow command blocks are exercised locally: three review drivers,
three golden-report checks and three Node/Python comparison checks. The local
command driver deliberately continues after an injected exit 7 to verify those
commands do not depend on a passing earlier test. This does **not** demonstrate
hosted failure scheduling or cancellation. Java transport and scanner commands
are outside that bounded command execution. Separately, the configured scoped
Ruff, formatting and Bandit checks pass. The retained JSON records exact
outcomes, workflow bytes and output fingerprints; it does not attest execution.

The [P15 readiness inventory](../p15-readiness-v1.md) still correctly records
unfinished procedure-content, installed-distribution and P19 help/acceptance
software. Its physical and independent customer gates remain unmet. This workflow
correction supplies no hardware, uptime, cryptographic certification or product
acceptance claim. Full lane completion remains false.
