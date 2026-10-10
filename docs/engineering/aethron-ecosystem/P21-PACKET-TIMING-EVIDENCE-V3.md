# C01 worker timing evidence admission — V3, partial

Decision: **FIX malformed diagnostic duration admission.** The packet comparison
probe previously accepted any worker-reported binary64 CPU duration, including
NaN, infinity and negative values. Output parity cannot validate timing metadata.
The probe now rejects nonfinite or negative durations before retaining the value
for aggregation. Finite zero and positive values remain accepted. No upper bound
is invented; this check does not authenticate the worker or its clock.

Two new test methods use a synthetic response and in-memory pipes without
launching Node or running a sensor benchmark. Four malformed-duration subcases
failed before the change; zero and positive controls passed. The first test
attempt also had two positive-control errors from an incorrect field name; these
were corrected before the retained RED run (four failures, zero errors).
Five packet evidence test methods pass after the fix, including the existing
optimization-mode and result-parity controls.

Production packet code, candidate kernels, Node worker and aggregation arithmetic
are unchanged. Four source hashes from the original C01 V2 report match its
original review commit. That historical byte check does not requalify timing
observations or satisfy the fresh technology reassessment. Raw timing samples
are not added or reconstructed, and historical reports remain unchanged.

This is diagnostic evidence admission, not a runtime technology selection. Full
V3 reassessment remains incomplete at C01. No performance improvement, physical
sensor validation, hard deadline or operational capability is claimed. See
[source-bound checks](evidence/phase2/packet-timing-evidence-v3.json).
