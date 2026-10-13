# C01 comparison worker startup cleanup — V3, partial

Decision: **FIX diagnostic worker ownership during construction.** A worker was
created before validating its handshake and reading startup metadata. When
either operation failed, construction never returned, so the caller's `finally`
could not call `close()`. The harness now invokes its existing cleanup path on
post-creation initialization failure, including interrupts, then propagates the
failure. Production packet processing, candidate decoders, worker program,
measurement arithmetic and successful-startup behavior are unchanged.

Three new test methods use fake processes and in-memory pipes. Invalid handshake,
read timeout, interrupt and malformed RSS metadata produced four RED assertion
failures with no execution errors. A successful-startup control already passed.
All eight packet evidence methods pass after the fix. Ruff and format pass;
Bandit retains nine existing LOW findings for subprocess calls and assertions.
No Node process, performance matrix, physical sensor or network transport was
exercised by these new checks.

Python's [subprocess documentation](https://docs.python.org/3/library/subprocess.html)
describes explicit process waiting and pipe ownership. This change adds the
missing call to the harness's cleanup path; it does not prove process termination
under every failure. Cleanup exceptions can supersede the startup exception,
with its context retained. `close()` still closes stdin before its wait/finally
block and uses an untimed wait after kill. Those cleanup-failure boundaries need
separate review; no hard shutdown or resource guarantee is asserted here.

C04 registration comparison was also inspected for the preceding tracing defect:
it does not use allocation tracing, so no tracing-lifecycle fix applies there.
That observation is not a full registration review. Full V3 review remains
incomplete at C01. No production KEEP/MIGRATE decision, qualification result or
completion marker is added. Historical reports remain unchanged. See
[source-bound checks](evidence/phase2/packet-startup-evidence-v3.json).
