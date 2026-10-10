# C02 report fingerprints — V3, partial

Decision: **FIX report provenance.** Comparison output identified payload size
and summary measurements but omitted exact source and payload fingerprints.
Reports now include SHA-256 of the comparison file, the actual imported replay
module's on-disk file, and the complete synthetic payload. An installed module
is read from its own import location; a repository copy is not substituted.
Output uses logical labels without absolute source paths. Missing files abort
before temporary-file creation; hashing is outside timing and tracing passes.

This small offline reporting correction has narrow constraints: local trusted
files, already resident bytes, no hard deadline, no added runtime or dependency.
Python [hashlib](https://docs.python.org/3.13/library/hashlib.html) hashes those
bytes in process. Node [crypto](https://nodejs.org/api/crypto.html) also provides
hashing, but a separate hashing exchange adds serialization without improving
the desired byte fingerprint semantics. This scoped choice is not a production
replay technology decision or a performance claim.

Three new tests substitute all candidate functions, clocks, tracing calls and
temporary-file creation. They exercise report assembly with a fixed synthetic
1 MiB payload, a known digest for an alternate imported-source file, omitted
absolute paths, and missing-source rejection. Three assertions failed before the
change; all eight focused methods pass afterward. Ruff/format pass. Two LOW
Bandit findings match the preceding source by rule, severity and message. All
candidate/stream ASTs and `main` except its report assignment are unchanged.
No actual candidate benchmark results were produced by the new tests.

Fingerprints describe on-disk bytes, not loaded executable attestation or report
authentication. Imports precede hashing, and concurrent mutation is not excluded.
The manifest omits transitive dependencies and the separately invoked JSON
counterexample probe; it is not an atomic or complete environment snapshot.
Historical reports remain untouched and cannot be retrospectively qualified by
this change. Full V3 production review remains incomplete at C01; this is only
an evidence-integrity correction. No audit completion marker is created.

See [source-bound checks](evidence/phase2/replay-source-evidence-v3.json).
