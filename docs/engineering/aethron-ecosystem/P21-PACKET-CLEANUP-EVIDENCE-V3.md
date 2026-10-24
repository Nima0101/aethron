# C01 diagnostic cleanup failure paths — V3, partial

Decision: **FIX cleanup control flow.** The comparison harness closed stdin
before entering its cleanup `finally`, so a close failure skipped process
waiting and output-pipe closure. A poll, kill or post-kill wait failure skipped
both output closes; stdout close failure skipped stderr. The second process
wait also omitted a timeout.

Nested `finally` blocks now attempt waiting after stdin close fails and both
output closes after process cleanup fails. The post-kill wait has the same
five-second timeout argument as the initial wait. Errors are not suppressed;
a later cleanup error may supersede an earlier one with exception context.
The constructor, decoders, measurement arithmetic and worker program are
unchanged. This fixes the diagnostic harness only, not P1 process isolation or
any production sensor runtime.

Five new methods exercise broken stdin closure and interrupts, poll/kill/wait
errors, stdout closure errors, first/second wait timeouts and normal completion.
RED produced eight assertion failures and no execution errors; the normal
completion control passed before the correction. All thirteen packet evidence
methods pass after the fix. Tests use fake processes and pipes without launching
Node or timing a sensor algorithm. Ruff/format pass; the nine LOW Bandit findings
match the preceding source exactly by rule, severity and message. All functions
except `Node.close` have unchanged ASTs.

Python's [subprocess documentation](https://docs.python.org/3/library/subprocess.html)
distinguishes process waiting, timeout exceptions and termination. Passing a
timeout to both waits does not bound pipe closure or OS scheduling and does not
guarantee that kill/wait succeeds. No OS-level shutdown measurement or resource
qualification is claimed. A failed cleanup can leave a child alive; callers must
not interpret failure as termination evidence.

This supersedes the current-code cleanup limitations described in the preceding
[startup review](P21-PACKET-STARTUP-EVIDENCE-V3.md); that historical review and its
source hashes remain unchanged. Full V3 review remains incomplete at C01. No
runtime KEEP/MIGRATE decision or completion marker is added. See
[source-bound checks](evidence/phase2/packet-cleanup-evidence-v3.json).
