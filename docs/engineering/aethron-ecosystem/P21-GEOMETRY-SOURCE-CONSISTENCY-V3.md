# C03 geometry source consistency — V3, partial

Decision: **FIX source observation timing and report admission.** The harness
previously hashed sources after admission checks and never rechecked them.
Changes during admission could become the reported starting state; changes or
removals during measured work did not prevent report output.

Initial fingerprints now precede camera construction and admission checks,
after the existing caller-tracing guard. The two captured source paths are read
again after batches and tracing cleanup. Changed digests raise
`geometry_audit_source_changed`; read errors propagate. Neither emits JSON.
Missing initial sources prevent camera construction.

Three new methods produced seven RED assertion failures with zero execution
errors: four changes across admission/measurement and both paths, two removals,
and one late initial-read control. All 12 focused methods pass after correction.
New controls use tiny temporary source files and inert cameras; change/removal
controls also use fake clocks and tracing. They are report-admission checks,
not a geometry benchmark or accuracy result. Existing unchanged-source controls
remain green. Ruff passes. One formatting-only blank line was corrected and the
format check passes. Bandit retains four LOW findings across harness and tests,
unchanged by rule, severity and message from the baseline.

The full measurement batch loop and non-main code have identical ASTs before
and after the change. Geometry implementation, candidate algorithms, admission
vectors, measurement arithmetic and historical results remain unchanged.
The report still covers only admission and warm-up parity; measured outputs are
not individually compared. No prior negative evidence is removed.

The [hashlib contract](https://docs.python.org/3.13/library/hashlib.html) describes
digests of supplied bytes. These before/after observations cannot detect changes
restored between reads or changes after the last read. They do not attest loaded
code, dependencies or authenticity and are not an immutable execution snapshot.
Historical reports are not requalified.

This is an evidence-tool correction, not a new component or technology selection.
Full V3 reassessment remains incomplete at C01; no new KEEP/MIGRATE decision,
completion marker or forward feature expansion follows from these tests.
See [source-bound checks](evidence/phase2/geometry-source-consistency-v3.json).
