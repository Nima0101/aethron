# C03 geometry comparison evidence integrity — V3, partial

Decision: **FIX optimized-mode admission; CLARIFY measured-call parity.** This
corrects a diagnostic evidence boundary. Production geometry and candidate
arithmetic are unchanged. The full V3 technology review remains incomplete at
C01; no new runtime KEEP/MIGRATE decision is recorded.

The probe uses assertions to compare admission vectors and warm-up outputs.
Optimized Python removes those checks while the report still declares parity.
An explicit module guard now rejects optimized execution/import before exposing
the comparison entry point. Imports still run before the guard; it is not a
sandbox or protection against edited source. Four subprocess cases (`-O`,
`-OO`, `PYTHONOPTIMIZE=1/2`) previously returned success with unchecked helpers;
they now fail with no report on stdout. Two normal-mode controls inject a
mismatched admission outcome and a failing warm-up comparison. Both stop before
measurement/reporting. The warm-up control also traverses the existing 22
synthetic admission vectors. No performance matrix or hardware test was run.

The existing `parity` field covers those premeasurement comparisons. Timed
repetitions discard their outputs; traced outputs are also not compared. It
therefore cannot establish parity of every measured call. The README now says
this explicitly and distinguishes aggregate measurements from retained raw
samples. Historical reports and source hashes remain unchanged and tied to their
original revisions. This guard does not requalify them or validate their timing.

The failure follows official [Python assertion semantics](https://docs.python.org/3/reference/simple_stmts.html#the-assert-statement)
and [optimization options](https://docs.python.org/3/using/cmdline.html#cmdoption-O).
This evidence correction retains the diagnostic harness without endorsing a
production runtime or adding an operational migration. The full reassessment,
including comparative technology decisions, is not complete.

See [source-bound checks](evidence/phase2/geometry-evidence-review-v3.json).
