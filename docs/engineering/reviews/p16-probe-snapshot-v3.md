# P16 comparison probe source consistency review v3

Baseline: `3fbb37727cfcb04ef8e762e2e80725949764c4ab`. Reviewed 2026-10-10.
Decision: **KEEP direct byte inspection and standard SHA-256; FIX observable source drift**.
The tracing bridge was verified against its parent, five file hashes and noreply identity.
The fresh walk re-read the earliest passport parser, trust and evidence implementation;
no admission change was demonstrated. This correction concerns the comparison driver.

## Constraints and technology reassessment

The offline local driver reads five fixed trusted project paths and calls the existing
verifier plus a Node primitive comparison. It must associate the fixture digest with
the bytes actually parsed and reject changes visible across the run. These files are
local trusted tooling inputs, not a network upload API or sandbox for hostile files.
There is no required throughput, physical target or atomic filesystem snapshot service.

| Candidate | Evidence and decision |
|---|---|
| Python immutable bytes and hashlib | [Official API](https://docs.python.org/3.13/library/hashlib.html) hashes supplied bytes. Direct comparison of retained bytes can detect a changed final read without a second parser, subprocess or timestamp assumption. KEEP for this local diagnostic. |
| Filesystem metadata checks | [stat metadata](https://docs.python.org/3.13/library/os.html#os.stat_result) exposes size and timestamps; my assessment is that these do not establish byte equality. Not selected as the content check. |
| Java/Kotlin MessageDigest | [Official API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/MessageDigest.html) supports SHA-256 over supplied bytes. Credible outside the incumbent languages, but another process performing the same reads adds no atomicity or loaded-code evidence. No measured advantage establishes migration. |
| Git tree archive and isolated runner | [git archive](https://git-scm.com/docs/git-archive) can export a named tree. Appropriate for separate committed-tree reproduction; it does not exercise this uncommitted working copy or attest interpreter/native dependencies. No archive or isolated runner was built here. |

The selection is based on byte identity and inspection scope, not installed tools,
familiarity or rewrite cost. It is not a language speed comparison. Atomic execution
provenance would require a stronger runner contract and is not claimed by this change.

## Observed gap and executable correction

Previously the driver parsed vectors once and read files again for source hashes and
the fixture digest after execution. A persistent edit could therefore produce a success
report with hashes for bytes different from those consumed. Earlier source-scope prose
acknowledged non-atomic reads, but did not prevent this locally detectable mismatch.

One new regression method simulates a whitespace edit after comparison begins for each
of the five source paths, without editing disk. All five cases failed the required
rejection assertion on the old driver, with zero execution errors. The implementation
now retains initial bytes, parses that captured fixture, compares every final file read
with its retained value, and raises `probe_source_changed` before JSON output on mismatch.
The successful manifest and fixture digest use captured bytes. Failures occur after
tracing cleanup. Existing successful comparison and source digest controls remain active.

A test closure triggered Ruff B023 during verification; explicitly binding its per-case
state corrected the test. The production fix was unchanged. Initial sandbox namespace
and fork failures preceded the successful policy read; they are infrastructure failures,
not test passes or implementation failures.

The check cannot detect edits restored between reads, changes after the final read,
pre-existing loaded-module divergence, or unlisted dependency changes. It is not an
atomic snapshot, hostile-writer defense, signed attestation or dependency closure.
Captured source buffers precede allocation tracing and are excluded from its measured
interval; that metric is not whole-process memory. Fixed local paths have no newly
claimed file-size bound. Historical result files remain immutable.

[Source-bound results](p16-probe-snapshot-v3-results.json) retain RED/GREEN outcomes and
fresh comparison output. P16/P17/P18 review is incomplete. Next: comparison timing
accounting, including the limits of single-sample means and cross-runtime comparisons.
