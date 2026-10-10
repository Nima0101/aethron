# C02 replay source consistency — V3, partial

Decision: **FIX report admission after observed source drift.** The replay
comparison captured source fingerprints only before its measurement passes.
Changing or removing a source during the run did not prevent JSON publication.
The harness now retains both source paths and compares their final digests with
the initial digests after fixture cleanup. A mismatch raises
`replay_audit_source_changed`; a read error propagates. Neither emits a report.

Two new regression methods cover changed and removed harness/replay-module
files, with four RED assertion failures and zero execution errors before the
fix. All 10 focused methods now pass. New cases use tiny temporary source files,
synthetic constant candidate results, fake clocks/tracing and an in-memory
fixture file; they do not benchmark replay implementations. Existing unchanged
source and payload controls remain green. Ruff and formatting pass. Bandit
retains four LOW findings across harness and tests, unchanged by rule, severity
and message from the baseline. No clean security-scan claim is made.

The measurement/context block and all non-main code have identical ASTs before
and after this correction. Production replay code, candidates, sample count,
fixture bytes and measurement arithmetic are unchanged. Source reads occur
outside measured work. Historical reports and negative evidence are retained.

The [hashlib contract](https://docs.python.org/3.13/library/hashlib.html) binds a
digest to supplied bytes. The two reads are observations, not proof of immutable
execution: changes restored between reads or made after the final read can go
undetected. Fingerprints do not attest loaded code, dependencies or authenticity.
No historical result is retroactively qualified.

This is a local evidence-tool correction, not a new component or technology
selection. Full V3 reassessment remains incomplete at C01, with no forward
feature expansion, new KEEP/MIGRATE decision or completion marker.
See [source-bound checks](evidence/phase2/replay-source-consistency-v3.json).
