# P16 comparison probe tracing lifecycle review v3

Baseline: `d09e0fa84ef577c20997d0ae00e63104de57dc3c`. Reviewed 2026-10-10.
Decision: **KEEP the measurement technology; FIX tracing ownership and cleanup**.
This is a local assurance-tool correction, not a change to passport admission.

The fresh walk began at parser/canonicalization and signature/policy validation,
then re-read evidence binding, task, bundle, federation and inbox implementation.
Their bounded offline scope remains explicit; no new production defect was demonstrated
in that walk. The focused runtime and conformance regression baseline was rerun.
This record does not certify a completed re-audit of every document or phase.

## Requirements and technology choice

The current metric is Python-traced allocation peak during construction and rejection
of a near-limit JSON sample. The driver calls the actual Python verifier and compares
six signature cases with Node. It runs locally, serially, without a target-hardware
SLA. Timing loops precede allocation tracing. Caller tracing must not contaminate those
loops or the peak, and errors must produce no success report.

| Candidate | Evidence and decision |
|---|---|
| CPython tracemalloc | [Official API](https://docs.python.org/3.13/library/tracemalloc.html) exposes tracing state and traced allocation peaks. Stopping clears collected traces. Directly measures the declared allocation domain; KEEP with exclusive lifecycle checks. |
| Memray native profiler | [Official overview](https://bloomberg.github.io/memray/overview.html) covers Python, interpreter and extension allocations on Linux/macOS. Credible for a broader native-memory investigation; that is a different metric, not a transparent replacement for Python-traced peak. |
| C++ heaptrack collector | [Official repository](https://github.com/KDE/heaptrack) documents Linux heap allocation traces, separate analysis and C++ build dependencies. Credible technology outside the driver's Python/JavaScript languages. Native heap events and trace artifacts require a separate sampling contract; they do not fix ownership of this process's Python tracer. |
| Node process memory API | [Official API](https://nodejs.org/api/process.html#processmemoryusage) distinguishes process RSS, V8 heap and external allocations. Useful for its own subprocess, not this Python allocation interval. |

Selection follows the metric's allocation domain and portable API semantics, not
installed tooling or rewrite cost. No comparative profiler performance ranking was
measured. Broader native/RSS accounting would justify another instrument and separately
named evidence. This choice does not select P18 runtime technology.

## Reproduced mismatch and fix

The old driver neither rejected an existing tracing session nor used cleanup on failure.
Three regression methods produced four expected assertion failures: existing tracing was
accepted, RuntimeError and KeyboardInterrupt leaked tracing, and a peak-query failure
leaked tracing. The initial active-session test used an unwrapped verifier mock and
failed an unrelated admission assertion; its corrected RED uses the real verifier.
Both logs are retained. A subsequent Ruff B023 finding was fixed by binding the injected
exception to the test callback; no production behavior changed for that lint correction.

The driver now rejects tracing at entry before optional imports, verifier work or
subprocess launch. It leaves the caller's trace depth and retained allocation trace intact.
A try/finally stops the session it starts even when verification or peak reading fails.
Tests also exercise real `-X tracemalloc=3` startup, unchanged exception identity, empty
failure output, positive peak reporting and stopped tracing after successful calls.

This assumes a serial process without another thread changing tracer state during the
probe. It is not a lock against external instrumentation. Python-traced allocations do
not cover all native allocations or RSS; the sample includes input construction and
is not a demonstrated worst-case bound. Historical reports are preserved, not upgraded.
No hard real-time, hardware, CNSA, MLS or availability qualification follows.

[Source-bound results](p16-probe-tracing-v3-results.json) retain focused outcomes and the
actual local comparison sample. Whole-lane review remains incomplete. Next review:
comparison timing accounting and source-snapshot evidence boundaries.
