# C02 replay comparison evidence integrity — V3, partial

Decision: **FIX comparison admission with assertions disabled.** This review
corrects the evidence harness, not production replay processing or its technology
choice. Full V3 reassessment remains incomplete at C01; no new KEEP/MIGRATE or
physical/performance qualification is claimed.

Both measurement passes must compare every candidate's bytes with the fixture
before emitting a report. The existing assertions disappear under optimized
Python, permitting an unchecked comparison report. The module now rejects
optimized execution/import before exposing its report generator. The same gate
covers `-O`, `-OO`, and environment-selected optimization. Imports execute before
the gate; this is not an import sandbox or protection against edited source.

Four subprocess controls initially exposed unchecked helpers and returned zero
(four assertion failures, no execution errors). They now reject with no report
on stdout. Normal-mode controls substitute a deliberately wrong candidate on
the first timed call and on the first traced-allocation call. Both raise before
report output and leave tracing disabled. These bounded controls use the existing
1 MiB synthetic fixture and stop within two candidate calls; they do not run the
comparison matrix or create new benchmark evidence. All pre-existing comparison
AST is unchanged after excluding the new module guard.

The mechanism is documented by the official [Python assertion reference](https://docs.python.org/3/reference/simple_stmts.html#the-assert-statement)
and [optimization options](https://docs.python.org/3/using/cmdline.html#cmdoption-O).
Keeping this diagnostic harness for an admission correction is not a choice of
production sensor runtime. Operational migration/performance work is not part of
this patch. Historical reports, source bindings and JSON-parser counterexamples
remain unchanged; their retained revisions are not requalified by these tests.
The existing readinto prototype still lacks the full reader contract, and
aggregate timing cannot establish a hard deadline or physical qualification.

See [source-bound checks](evidence/phase2/replay-evidence-review-v3.json).
