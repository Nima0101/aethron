# C01 packet comparison evidence integrity — V3, partial

Decision: **FIX evidence admission under optimized Python.** This is a correction
to the comparison harness, not a runtime KEEP/MIGRATE decision. The full current
technology reassessment remains incomplete at C01; no completion marker or new
performance/physical qualification is produced.

The harness must refuse to expose results when its parity checks are absent.
Python optimization removes `assert` expressions, including the worker handshake
read and warm-up candidate calls. The timed-loop and fixture checks also vanish.
The module now rejects optimized execution/import before defining the helper
functions or starting a worker. Normal-mode calculations and checks are unchanged.
The guard covers `-O`, `-OO` and environment-selected optimization; it is not a
sandbox against a caller editing source or bypassing the harness.

Evidence: four optimized-import cases initially returned success and exposed
unchecked helpers (four assertion failures, zero execution errors). After the
explicit module guard they exit unsuccessfully with no report on stdout. Two
normal-mode controls independently reject a wrong warm-up and a wrong later
sample, and accept a constant result across one warm-up plus 15 samples. These
checks use inert candidate functions, not sensor kernels or a Node worker. They
do not produce new comparative timing evidence.

The failure mechanism follows the official [Python assertion semantics](https://docs.python.org/3/reference/simple_stmts.html#the-assert-statement)
and [optimization options](https://docs.python.org/3/using/cmdline.html#cmdoption-O).
The existing diagnostic runtime is retained for this bounded evidence correction;
this does not choose it for production processing. Operational technology
migration and historical benchmark requalification are outside this patch.
Historical source hashes and reports remain unchanged and identify their own
reviewed revisions, not this updated harness. Normal-mode reports still retain
aggregate timing only, and their existing CPU/IPC and qualification limitations
remain in the probe README.

See [source-bound checks](evidence/phase2/packet-evidence-review-v3.json).
