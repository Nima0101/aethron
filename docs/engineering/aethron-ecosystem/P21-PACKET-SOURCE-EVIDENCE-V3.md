# C01 report source and fixture fingerprints — V3, partial

Decision: **FIX report provenance.** The standalone comparison report recorded
versions and aggregate measurements but no source or exact fixture fingerprints.
A new report now identifies three on-disk files: the comparison script, worker,
and the packet module selected by the interpreter's actual import. It does not
substitute a repository copy for an installed module. Logical output labels avoid
publishing absolute installation paths. Missing source bytes prevent emission.

Each case identifies its payload bytes and layout JSON separately with SHA-256.
Layout serialization uses sorted keys, compact separators, UTF-8 and rejection
of nonfinite JSON numbers. Hashing is outside the measured samples. No decoder,
fixture generator, worker, parity loop or timing arithmetic changed. This is an
audit-report correction, not an operational sensor implementation or migration.

Constraints are offline execution on the existing Linux/macOS diagnostic host,
small trusted source files, two fixed payloads, no timing/deadline claim, and
identification of the bytes already available in the reporting process. Python
[hashlib](https://docs.python.org/3.13/library/hashlib.html) and Node
[crypto](https://nodejs.org/api/crypto.html) both expose SHA-256 over bytes.
For this small reporting change, hashlib hashes the existing in-process bytes;
a Node hashing path would require an additional exchange and interpretation of
those bytes without improving the intended fingerprint semantics. No new
runtime, dependency or toolchain is added. This scoped choice does not settle the
open production technology reassessment or claim a performance win.

Three new test methods use substituted measurement results and inert workers,
three-byte payloads and a temporary imported-source path. They check exact source
selection, a known SHA-256 vector, path omission, distinct per-case layout/payload
bindings and missing-source failure. Before the fix: four assertion failures,
zero execution errors. After: all sixteen focused methods pass. Ruff and format
checks pass; nine LOW Bandit findings match the preceding baseline. All existing
functions/classes except the report assembly in `main` retain identical ASTs.
No Node process or sensor benchmark was executed for these new checks.

These hashes do not authenticate the report or attest loaded executable code.
Files are read after imports and may change during execution; the manifest is
not an atomic snapshot. Dependencies, interpreter and native libraries are not
fully covered. Historical measurements remain unmodified and cannot acquire
retrospective execution provenance from current source hashes. Full V3 review
remains incomplete at C01, with no new production KEEP/MIGRATE decision or audit
completion marker. See [source-bound checks](evidence/phase2/packet-source-evidence-v3.json).
