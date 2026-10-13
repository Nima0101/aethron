# C06 recorded raster diagnostic limits — V3, partial

Decision: **CLARIFY fixed-message and exception privacy limits.** Existing
sampling and result-record reviews establish neither exception-object redaction
nor fault containment. The module documentation now states these limits; runtime
behavior is unchanged. Full technology reassessment remains incomplete at C01.

The remapping wrapper converts ValueError, TypeError, AttributeError and
OverflowError to ValueError with the fixed `invalid_raster_rectification`
message. It suppresses implicit context display, but the original exception
remains accessible through `__context__`. Exception objects and traceback state
must not be treated as sanitized diagnostic records. The fixed string is not an
authorization boundary or a guarantee about a caller's logging/serialization.
[Python's exception-context reference](https://docs.python.org/3.13/library/exceptions.html#exception-context)
documents this distinction; it was inspected for this review.

The catch list is intentionally narrower than all possible faults. Injected
RuntimeError and MemoryError propagate, as do KeyboardInterrupt and SystemExit.
This library therefore does not promise to convert every failure to a fixed
message or to provide process isolation/recovery. No broader catch, exception
mutation, scheduling, watchdog, geometry or sensor-admission change is made.

Two added methods cover both entry points and eight exception classes, for 16
injected cases. They fail validation before pixel processing. They check fixed
message/context behavior and preservation of unhandled exception identity.
All five claim-control methods pass before and after the documentation change.
These are controls of existing behavior, not a RED production bug fix. No
out-of-memory event or real process signal was generated, and the tests do not
establish operating-system signal timing, crash recovery or privacy of arbitrary
traceback tooling.

Ruff and formatting pass; scoped Bandit has zero findings. The module AST is
identical to the parent after removing docstrings. Historical evidence remains
unchanged; no sensor accuracy, performance, hardware, compatibility or runtime
selection claim is introduced. See [source-bound review checks](evidence/phase2/raster-diagnostics-v3.json).
