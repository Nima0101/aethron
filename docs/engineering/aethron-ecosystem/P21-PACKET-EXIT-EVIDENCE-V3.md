# C01 comparison worker completion — V3, partial

Decision: **FIX report admission after abnormal worker exit.** The harness
waited for and closed the comparison worker but ignored its return code. A
worker that returned matching sample results and then failed could still yield
a report with parity=true. Report acceptance now checks for exit status zero
after cleanup, before appending a case or printing the complete JSON report.
Nonzero or unconfirmed status raises the fixed audit_worker_exit error.
Cleanup errors retain their existing propagation behavior.

The focused regression substitutes inert fixtures, measurements and a fake
worker. Positive exit 1, signal-style exit -9 and unconfirmed status None each
initially failed the expected-rejection assertion (three failures, zero errors).
All three now reject with empty stdout; zero exit admits both complete cases.
All 18 packet-audit test methods pass, including existing optimization, timing
admission, source binding and process-cleanup controls. The new report controls
do not spawn Node, run a sensor decoder or collect benchmark measurements.

Ruff and formatting pass. Bandit reports 11 LOW findings across harness and
tests, identical by rule, severity and message to the pre-change source; no
clean security scan is claimed. The harness AST differs only by the two-line
post-cleanup admission guard. Production packets, worker code, fixture
construction, comparison candidates, timing arithmetic and existing reports
are unchanged. No claim about actual OS shutdown or physical timing is added.

Python's official [subprocess documentation](https://docs.python.org/3.13/library/subprocess.html#subprocess.Popen.returncode)
(inspected 2026-10-10) defines returncode and its completion/signal semantics.
This corrects existing audit evidence handling, without introducing a component
or selecting a runtime. The full open-universe reassessment remains incomplete
at C01; no KEEP/MIGRATE decision or completion marker follows from these checks.
Historical negative evidence remains preserved and is not requalified.

See [source-bound checks](evidence/phase2/packet-exit-evidence-v3.json).
