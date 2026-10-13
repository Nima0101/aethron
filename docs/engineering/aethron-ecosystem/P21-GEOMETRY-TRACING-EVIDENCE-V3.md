# C03 comparison tracing ownership — V3, partial

Decision: **FIX diagnostic tracing lifecycle.** The comparison could accept an
existing trace session, include earlier allocations in its peak and clear the
caller's traces. A candidate exception, interrupt or failed peak read left its
own tracing active. Subsequent timings in that interpreter could be affected.

The entry point now rejects preexisting tracing before camera construction and
uses `finally` to stop each owned allocation pass. Production geometry and the
NumPy candidate, numerical tolerances, fixtures and timing loops are unchanged.
The existing report's parity field still covers admission and warm-up only;
individual timed/traced results are not checked. Historical reports are unchanged.

Four new methods exercise tracing admission, candidate failure/interrupt, peak
read failure and successful report cleanup. They substitute inert cameras; no
geometry timing matrix is executed. RED produced four assertion failures and no
execution errors; the inert success control already passed. All seven focused
methods pass after the fix, including existing optimized-mode and parity-failure
controls. Formatting needed correction; Ruff then passed. Bandit retains the two
existing LOW assertion findings. The optimized-mode guard remains exercised.

Python's [tracemalloc documentation](https://docs.python.org/3/library/tracemalloc.html)
describes traced allocation peaks and the trace-clearing effect of `stop()`.
This harness assumes exclusive process ownership of that diagnostic state; the
entry check is not thread synchronization. Traced peaks do not measure total
process/native memory or establish hardware resource bounds.

This is evidence-integrity maintenance, not a new runtime selection or a
production performance result. Full V3 component review remains incomplete at
C01; no completion marker or KEEP/MIGRATE decision is added. See the
[source-bound checks](evidence/phase2/geometry-tracing-evidence-v3.json).
