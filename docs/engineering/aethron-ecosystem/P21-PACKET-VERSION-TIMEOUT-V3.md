# C01 runtime metadata query — V3, partial

Decision: **FIX missing timeout request for runtime metadata.** The comparison
harness queried node --version without a timeout before starting fixture work.
It now requests five seconds, matching the existing child-wait timeout scale.
This is a diagnostic subprocess policy, not a measured latency acceptance bound.
The command, output handling and error propagation remain unchanged.

The new timeout regression initially failed one assertion because the subprocess
call lacked timeout=5. After correction it passes. A second method injects spawn,
nonzero-exit and timeout failures: each original exception propagates, stdout
remains empty, and neither fixtures nor comparison workers are created. The
successful report controls remain covered by the existing focused suite.
All 20 packet-audit methods pass. These new controls mock the query and do not
launch Node, wait five seconds or measure OS termination behavior.

Ruff and formatting pass. Bandit retains 11 LOW findings across harness and tests,
identical by rule, severity and message to the baseline; no clean security scan
is claimed. The harness AST differs only by the timeout keyword. Production
sensor code, worker, candidates, fixtures, timing arithmetic and historical
reports are unchanged. No operational benchmark is run or requalified.

The official [subprocess documentation](https://docs.python.org/3.13/library/subprocess.html)
explains timeout propagation and that process creation may delay timeout handling.
The five-second request does not cap total elapsed time, output volume or all
resource use, and does not authenticate a PATH-selected executable. A failing
query still prevents report publication; it does not prove cleanup of arbitrary
process descendants or justify a real-time claim.

This is a correction to existing evidence tooling, not a new component or
runtime selection. Full V3 technology reassessment remains incomplete at C01;
no KEEP/MIGRATE decision or completion marker is introduced. Historical negative
evidence is preserved. See [source-bound checks](evidence/phase2/packet-version-timeout-v3.json).
