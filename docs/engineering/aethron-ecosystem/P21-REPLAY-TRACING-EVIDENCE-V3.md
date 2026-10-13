# C02 comparison tracing ownership — V3, partial

Decision: **FIX diagnostic tracing lifecycle.** The replay comparison previously
started tracing without rejecting an existing session. It could therefore mix
preexisting allocations into its peak or stop the caller's tracing. A candidate
exception or failed peak read also left the harness's tracing enabled, affecting
later timing calls in that interpreter. This is a comparison-harness defect;
production replay code is unchanged.

The harness now rejects an active trace session before creating the fixture or
temporary file. It leaves that session and retained traces intact. A `finally`
block stops tracing started by the harness even when a candidate raises,
including an interrupt, or the peak read fails. Timing, sample count, fixture,
result parity and candidate algorithms are unchanged.

Three new test methods produced four RED assertion failures and no execution
errors: active-session admission, candidate exception, candidate interrupt and
peak-read failure. Synthetic candidates read bytes without invoking production
replay; each failing run stops at its first allocation pass. Five focused methods
pass after the fix, including the existing optimized-mode and wrong-result
controls. No performance matrix, Node process, VM or physical sensor was run.

Python's [tracemalloc documentation](https://docs.python.org/3/library/tracemalloc.html)
describes current/peak traced allocations and the trace-clearing behavior of
`stop()`. This process-global diagnostic API requires exclusive ownership for
these comparisons. The admission check does not synchronize against concurrent
threads starting or stopping tracing. Traced allocations do not represent total
process memory, native allocations or a hard resource ceiling.

This narrow cleanup does not select a production runtime or requalify historical
timing reports. Full V3 review remains incomplete at C01. See
[source-bound checks](evidence/phase2/replay-tracing-evidence-v3.json).
