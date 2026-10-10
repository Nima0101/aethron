# C01 diagnostic test isolation — V3 correction

The packet audit fixtures replaced shared `subprocess` attributes, `Path`
methods, `packets.__file__`, and `sys.stdout`. Other code in the same interpreter
could observe those replacements while a fixture was active, even though the
patches restored the originals afterward. This review establishes shared-binding
interference; it does not reproduce a concurrent failure or resolve another
component's hosted CI failure.

FIX: replace dependencies only in the independently loaded harness function's
namespace. Supply a local packet source descriptor, subprocess doubles, and
startup-path doubles; capture output through a local `print` binding. Keep the
real shared module/class attributes and output stream unchanged. Assertions now
check those shared bindings inside the active fixture scopes. This follows
[Python's namespace patching guidance](https://docs.python.org/3.13/library/unittest.mock.html#where-to-patch).

Validation on the local CPython 3.13.13 environment:

- RED: the added isolation assertions produced 22 failures across 12 of the
  existing 22 methods. Failures identified replaced shared bindings.
- GREEN: all 22 methods passed after narrowing the fixtures, including the
  existing cleanup, timeout, exit, source-change and no-report checks.
- Ruff lint and format checks passed. Bandit retained the two existing LOW
  findings for the subprocess import and bounded interpreter invocation.

Only tests change. The comparison harness, worker, sensor runtime, wire
contracts, historical evidence and frozen limits remain byte-for-byte unchanged
by this correction. No new benchmark, hardware qualification, real-time or
availability claim is made. This is a partial C01 review; the full technology
reassessment remains incomplete at C01. The next fixture-isolation review is C02
binary replay.
