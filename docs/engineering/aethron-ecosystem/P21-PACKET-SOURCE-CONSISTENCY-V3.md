# C01 source fingerprint consistency — V3, partial

Decision: **FIX report admission after observed source drift.** Source hashes
were captured only before the comparison. A file changed or removed during the
run could leave an apparently complete report with only the earlier fingerprint.
The harness now retains the three source paths and reads their SHA-256 digests
again after worker cleanup, before emitting JSON. A differing digest raises
`audit_source_changed`; read failures propagate. Neither emits a report.

Two regression methods cover changes and removals for the harness, worker and
imported packet module paths. All six cases initially failed assertions, with
zero execution errors. With the guard, all 22 focused methods pass. The new cases
use tiny temporary source files, fake fixture/results and worker cleanup callbacks;
no sensor benchmark or Node process is run by these cases. Existing unchanged
source/report controls still pass. After fixing four lint findings in test loop
callbacks, the two affected methods pass again. Ruff and formatting pass. Bandit
retains the same 11 LOW findings by rule, severity and message as the baseline.

The source-path extraction and final check leave candidate algorithms, worker,
fixtures, measured sections, sensor implementation and historical reports unchanged.
This is an evidence-tool correction, not a runtime selection or performance result.
Full V3 technology reassessment remains incomplete at C01. No completion marker
or new KEEP/MIGRATE decision is justified by these checks.

[Python hashlib](https://docs.python.org/3.13/library/hashlib.html) specifies that
the digest describes the supplied bytes. The before/after equality check does
not prove that sources stayed unchanged between reads, match loaded code, or
remain unchanged after the last read. It does not authenticate the files or
cover dependencies. Historical reports are not requalified. This guard detects
observed drift, not an immutable execution snapshot.

See [source-bound checks](evidence/phase2/packet-source-consistency-v3.json).
