# C07 recorded intensity diagnostic limits — V3, partial

Decision: **CLARIFY nested exception privacy and fault-containment limits.**
The API documentation now explains that a fixed validation-error message is not
a sanitized exception object. Production behavior is unchanged. Full V3
technology reassessment remains incomplete at C01; this is not a runtime
KEEP/MIGRATE decision or a new feature.

The wrapper catches ValueError, TypeError, AttributeError and OverflowError and
raises `invalid_intensity_replay` with context display suppressed. This may wrap
an already suppressed remapping exception. Both underlying exception objects
remain reachable by introspection. A fixed outer message does not erase nested
private details, traceback state or caller-held data. Do not serialize exception
objects or frame locals as privacy-safe diagnostics.

Python's [exception-context reference](https://docs.python.org/3.13/library/exceptions.html#exception-context)
distinguishes display suppression from retained context. The two-encoding
control substitutes a remapper that raises a synthetic private error beneath a
fixed remapping message. The outer message stays fixed while both context links
remain accessible. It verifies wrapper behavior using synthetic counts, not the
actual remapping algorithm or a logging product's privacy guarantees.

A second method injects RuntimeError, MemoryError, KeyboardInterrupt and
SystemExit at each remapper seam and confirms propagation of the original object.
No real memory exhaustion, process signal or pixel mapping is executed. This
library function is not a process isolation/recovery boundary. Broad catches or
changes to signal behavior are not introduced.

The two new methods pass before the docstring change (ten injected cases); four
focused diagnostic/result-record methods pass afterward. No RED production defect
is claimed. Ruff, formatting and scoped Bandit pass with zero findings. Removing
docstrings gives an AST identical to the reviewed parent. Calibration, hash
bindings, schemas and processing are unchanged. Historical failures and reports
remain intact, with no hardware, performance, qualification or authenticity claim.
See [source-bound checks](evidence/phase2/intensity-diagnostics-v3.json).
