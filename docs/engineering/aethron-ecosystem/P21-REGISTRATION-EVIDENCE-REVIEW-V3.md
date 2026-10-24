# C04 registration comparison evidence integrity — V3, partial

Decision: **FIX optimized-mode admission and overwritten iteration evidence.**
This changes comparison checks only. Production registration, calibration and
candidate arithmetic are unchanged. Full V3 technology reassessment remains
incomplete at C01; no new runtime KEEP/MIGRATE decision is recorded.

The harness overwrote each candidate's outputs across 15 iterations, then checked
only the last values. An early mismatch or early live-evidence flag disappeared
when later outputs were correct. The harness now starts an output set per
iteration and compares its complete results and non-live status before allowing
the next iteration. Checks run outside each candidate's timed region. They can
still alter later cache/contention conditions, so old timings are not relabeled
as results of the updated harness.

Optimized Python also removed both assertions while report parity remained true.
An explicit module guard now rejects optimized execution/import before exposing
the comparison entry point. Imports precede the guard; it is not a sandbox or a
security boundary against callers modifying source.

Six RED assertion failures were observed: four optimization modes, an early
candidate mismatch, and an early iteration where every result was marked live.
The same late-iteration mismatches were already rejected. After the correction,
all four test methods pass: four optimized subprocess cases, four early/late
mismatch cases and a positive consistent non-live report. These controls replace
Registration with inert result objects. They do not execute the projection
pipeline or provide new performance evidence. Fixture, candidate and projection
call-function ASTs remain unchanged.

The optimization mechanism follows the official [Python assertion reference](https://docs.python.org/3/reference/simple_stmts.html#the-assert-statement)
and [optimization options](https://docs.python.org/3/using/cmdline.html#cmdoption-O).
The diagnostic harness remains in place for this evidence correction; that is
not a production-runtime endorsement or completed comparative technology review.
Historical reports and source hashes stay unchanged. Their parity/non-live
claims cover final-iteration results only; this patch does not requalify earlier
measurements, physical calibration, accuracy, latency or live authority.

See [source-bound checks](evidence/phase2/registration-evidence-review-v3.json).
