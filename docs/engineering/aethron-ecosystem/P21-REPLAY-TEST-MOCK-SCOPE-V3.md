# C02 replay diagnostic mock scope — V3 correction

The diagnostic tests redirected the interpreter's shared `sys.stdout`, replaced
`replay.__file__`, and patched shared `tempfile.TemporaryFile` and
`tracemalloc.get_traced_memory` attributes. Unrelated code could observe those
replacements while the fixtures were active.

FIX: supply source metadata, output capture, file-creation and peak-reading
doubles through the loaded harness function's own namespace. Check the original
shared bindings inside each active fixture scope. This follows
[Python's namespace patching guidance](https://docs.python.org/3.13/library/unittest.mock.html#where-to-patch).

The added assertions produced 13 RED failures across nine of ten existing test
methods. After narrowing the mocks, all ten methods passed on local CPython
3.13.13, including source mutation/removal rejection, tracing rejection and
cleanup, payload binding, parity failures and optimized-import rejection.
Ruff lint/format checks passed. Bandit retained the two existing LOW findings
for the subprocess import and bounded interpreter invocation.

The initial mock-scope correction left real tracing tests in the runner's
interpreter. A subsequent regression started a three-frame runner trace and
retained an allocation before invoking all four tracing cases. The four cases
reported success, but the regression failed: tracing was stopped, the allocation
trace was erased, and the traceback limit had changed to one. Python documents
that [`tracemalloc.stop()` clears recorded traces](https://docs.python.org/3.13/library/tracemalloc.html#tracemalloc.stop).

FIX: run each of the four existing test bodies in a fresh interpreter. A child
must report exactly one executed test, no skips and a successful exit. Preserve
the original assertions and negative cases; AST comparison confirmed all four
bodies are unchanged. Child environments remove inherited tracing/optimization
settings without modifying the parent environment. Each case has a 15-second
subprocess timeout; the runner-preservation regression has a 60-second timeout.
These are test timeouts, not a hard real-time or process-tree deadline claim.

The complete focused suite now passes all 11 methods. The new regression verifies
all four public cases succeed while the runner's original allocation traceback,
active tracing state and three-frame limit survive. Ruff passes. Bandit reports
four LOW findings: the two earlier findings plus two subprocess calls added for
isolation. Both new calls use the current interpreter, fixed test code, argument
lists without a shell and explicit timeouts. No finding is suppressed and no
hosted CI repair is claimed.

This correction changes only tests. Replay implementation, comparison harness,
contracts, historical measurements and frozen thresholds are unchanged. No
performance or qualification evidence is added. Full V3 technology reassessment
remains incomplete at C01; this is a partial C02 test review.
