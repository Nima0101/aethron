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

The tests that verify real tracing ownership still start/stop the interpreter's
real tracer. Narrowing function mocks does not isolate that process-global
state. The next C02 test task is to verify isolation from an already-active
runner tracer. No concurrent failure or hosted CI repair is claimed here.

This correction changes only tests. Replay implementation, comparison harness,
contracts, historical measurements and frozen thresholds are unchanged. No
performance or qualification evidence is added. Full V3 technology reassessment
remains incomplete at C01; this is a partial C02 test review.
