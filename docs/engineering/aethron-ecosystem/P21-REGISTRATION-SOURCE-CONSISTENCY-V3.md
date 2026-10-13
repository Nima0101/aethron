# C04 registration source consistency — V3, partial

Decision: **FIX report admission after observed source drift.** The comparison
already read sources before fixture construction, but did not observe them again.
Changes or removals during comparison did not prevent a JSON report carrying
the earlier fingerprints. The harness now retains the two source paths and
rechecks their digests after all iterations and temporary method patches finish.
A mismatch raises `registration_audit_source_changed`; read errors propagate.
Neither failure emits JSON. Initial read ordering is preserved.

Two new methods cover changes and removals for both paths. Four RED assertions
failed before correction, with zero execution errors. All eight focused methods
pass after correction. New cases use tiny temporary source files and inert
registration outputs; they do not benchmark projection or establish calibration
accuracy. They also confirm that transform/digest method identities are restored
when final source rejection propagates. Existing successful report and parity
failure controls remain green.

Ruff passes. One long test assertion was reformatted and formatting now passes.
Bandit retains four LOW findings across harness and tests, unchanged by rule,
severity and message. The rotated measurement loop and non-main code have
identical ASTs before and after this correction. Sensor implementation,
candidate algorithms, parity/non-live checks, timing arithmetic, fixtures and
historical results are unchanged. No performance or clean security-scan claim
is made.

The [hashlib contract](https://docs.python.org/3.13/library/hashlib.html) describes
digests of supplied bytes. Before/after observations do not prove immutable
execution: restored intermediate changes and changes after the final read can
be missed. They do not attest loaded code, dependencies or authenticity.
Historical reports are not requalified.

This is an evidence-tool correction, not a new component or runtime selection.
Full V3 technology reassessment remains incomplete at C01. No new KEEP/MIGRATE
decision, completion marker or forward feature expansion follows from these tests.
See [source-bound checks](evidence/phase2/registration-source-consistency-v3.json).
