# P16 packaging diagnostic retention

Baseline `82e044e8ef66558f8a8519964e6ad42968276fe8`, reviewed 2026-10-10.
The current policy/review order were read in full. The parser, signature and pinned
policy source were reread before continuing packaging review. No new runtime defect
was identified; that observation is not a completed whole-phase technology audit.

The hosted P16 source-archive job had no selected diagnostic artifact. The workflow
now records actual checkout SHA separately from five named GitHub context fields,
the source-archive SHA-256, archive-check output, install output, dependency check,
installed-source check and installed vectors. An explicit eight-file allowlist is
uploaded even after a preceding step fails. Artifact existence never means PASS;
files may be missing, empty or partial. No workspace-wide upload or environment dump.

[ADR](../../decisions/p16-packaging-retention-v3.json): KEEP the pinned
[official artifact action](https://github.com/actions/upload-artifact/tree/b7c566a772e6b6bfb58ed0dc250532a479d7789f)
for the hosted runner service. The [general CLI API client](https://cli.github.com/manual/gh_api)
is a credible alternate orchestration tool, but requires service-specific integration;
job logs alone do not provide the selected downloadable bundle. No custom uploader
or new runtime is justified by this bounded diagnostic requirement.

Retention is requested for fourteen days; it is not permanent release storage.
The name includes event SHA, run ID and attempt. The recorded checkout SHA may be a
PR merge commit rather than the PR head. Consumers must check the run conclusion,
repository, revision and attempt; these files do not authenticate themselves.
[GitHub artifact documentation](https://docs.github.com/en/actions/tutorials/store-and-share-data)
describes the retention mechanism. Neither a digest nor uploaded context is a signed
provenance statement. This bundle does not retain the source archive or resulting wheel.

Explicit `shell: bash` selects GitHub's
[documented pipefail execution](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
A real local shell probe confirms successful output capture and exit-zero continuation,
then exit-23 capture without continuation. Its negative control removes pipefail and
observes the failure being masked. This is a shell-semantics probe, not a hosted build
or upload. No failing production regression test is claimed for a configuration gap.

Thirty focused methods pass without skips: parser/policy/signature tests and four ADR
conformance methods. Actionlint passes. [Source-bound results](p16-packaging-retention-v3-results.json)
retain the local observations. No hosted upload, new archive build, installation or
customer acceptance was performed locally. The earlier commit was verified against
its parent, staged file hashes and noreply identity before publication.

## C4 assurance views

Context:
```mermaid
flowchart LR
  Reviewer --> Evidence[Scoped packaging diagnostics]
  Evidence --> Run[Hosted job conclusion]
```

Containers:
```mermaid
flowchart LR
  Checkout --> Runner[Hosted Python and Bash]
  Runner --> Files[Eight selected diagnostic paths]
  Files --> Artifact[Temporary workflow artifact]
```

Components:
```mermaid
flowchart LR
  Context[Checkout SHA and run context] --> Upload
  Digest[Archive digest] --> Upload
  Checks[Command output with failure propagation] --> Upload
```

Code:
```mermaid
flowchart LR
  Command --> Tee[tee with pipefail]
  Tee --> Log[Named output file]
  Log --> Action[Pinned upload-artifact]
```

This correction is software assurance only; no command, communication, intelligence,
surveillance or reconnaissance feature is introduced. No MLS/CNSA, real-time,
availability or physical qualification follows. Insufficient information for tactical
deployment. Full audit, release and phase completion remain unestablished.

## Public claim review at 7e34cc6

Reviewed 2026-10-10 at `7e34cc66328d81281dccc802b8f3fed736bfb50e` after
rereading current policy, the earliest parser, seven public interop contracts,
the examples and configured workflow. The prior bridge's parent, nine file hashes
and noreply identity were verified before publishing it. No CI was polled.

CLARIFY: three public profiles described hosted checks in present tense without
distinguishing configured behavior from observed results. They now state that these
are configured jobs and link the [evidence boundary](../../architecture/interop/verification-evidence-v1.md).
That page maps seven APIs to their actual guarantees and caller responsibilities,
and maps all three jobs to their source/installed/optional-dependency boundaries.
The sensor job's final consumer tests use checkout imports, not installed producer
modules. Diagnostic artifacts do not contain the archive or wheel and can exist
after failed checks. Historical evidence remains unchanged.

This is documentation reconciliation, not a new runtime, test framework or technology
selection. Existing component decisions retain their stated scopes and limitations;
no new migration benefit or runtime defect was demonstrated. No duplicate contract,
language, service or assertion-only documentation regression test was introduced.

Eight selected methods pass with zero skips: one lexical method, four real delivery
traces, two independent-floor counterexamples and one actual-signature method.
Both existing README Python snippets execute successfully with current source imports;
they report `authenticated`/`bound` while denying motion authority and evidence
qualification. This does not rerun installation instructions or a hosted job.
Twenty relative file links in the four affected public pages resolve locally.
Whitespace checks pass. No source/configuration changed, so runtime lint/security
results from earlier revisions are not relabeled as new checks.

The [current result record](p16-claims-current-v3-results.json) binds the reviewed
files and local logs. Source hashes are not loaded-code attestation or dependency
closure. C4 assurance views above remain descriptions of configured components;
they do not prove execution or deployment. The next executable work is to derive
requirements and compare technologies for the missing P16 durable caller-floor
boundary, after reconciling this documentation correction. Full lane completion
and tactical qualification remain unestablished.
