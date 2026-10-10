# C03 diagnostic test tracing — V3 correction

Seven geometry diagnostic cases require an idle tracer or exercise real tracing
ownership. Running them in the suite runner's interpreter could erase a trace
owned by that runner. A new regression started a three-frame trace and retained
an allocation before running the seven cases. All seven reported success, but
the regression failed: tracing was stopped, the retained traceback was erased,
and the frame limit had changed to one.

FIX: run each of those seven test bodies in a fresh interpreter. Each child must
exit successfully and report exactly one executed test with no skips. All seven
original test bodies are preserved exactly, verified by AST comparison. The
parent environment remains unchanged; child environments remove inherited
tracing and optimization settings. Each case has a 15-second subprocess timeout;
the runner-preservation regression has a 60-second timeout. These are test
limits, not hard real-time or process-tree deadline guarantees.

The regression now confirms that all seven public cases pass while the runner's
active state, three-frame limit and original allocation traceback survive.
This addresses the documented behavior that
[`tracemalloc.stop()` clears recorded traces](https://docs.python.org/3.13/library/tracemalloc.html#tracemalloc.stop).

Local CPython 3.13.13 verification: 13 methods PASS, Ruff lint/format PASS. Bandit
reports four LOW findings: two pre-existing findings and two new fixed
interpreter test launches. The new calls use argument lists, no shell and
explicit timeouts; no findings are suppressed. No hosted CI repair is claimed.

Only tests change. Geometry implementation, comparison harness, historical
evidence and frozen thresholds remain unchanged. Four other report-fixture tests
still patch shared source metadata/output bindings; reviewing those is the next
C03 test task. This is a partial test review, not a completed technology decision.
The full V3 technology cursor remains at C01.
