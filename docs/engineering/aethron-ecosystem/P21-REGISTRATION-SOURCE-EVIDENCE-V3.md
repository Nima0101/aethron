# C04 report source fingerprints — V3, partial

Decision: **FIX report provenance.** The registration comparison reported parity
and CPU summaries without identifying its harness or selected registration
source file. Reports now include SHA-256 of those on-disk files, following the
actual imported module location. Logical labels omit private absolute paths.
Missing source bytes prevent report emission. Hashing runs before calibration
fixture construction and outside timed samples.

This correction covers small trusted files on an offline diagnostic host,
without a latency target, added runtime or dependency. Python
[hashlib](https://docs.python.org/3.13/library/hashlib.html) hashes bytes directly
in the report process. Node [crypto](https://nodejs.org/api/crypto.html) offers
hashing too, but transferring these local bytes to a second runtime adds an
exchange without improving the intended fingerprint semantics. This scoped
reporting choice does not settle the production registration technology decision
or assert a performance win.

Two new methods reuse inert registration outputs, checking a temporary imported
source location against a known SHA-256 vector, exact harness bytes, private-path
omission, and missing-source failure without output. Before correction: two
assertion failures, zero execution errors. After: all six focused methods pass.
Ruff/format pass. Two LOW Bandit findings match the preceding source. The AST is
unchanged except for imports, the source-fingerprint assignment and the output
field; calibration, transform candidates, timing and parity checks are untouched.
These tests do not benchmark or qualify production registration.

The manifest describes on-disk source bytes after import, not loaded-code
attestation or report authentication. It is not an atomic snapshot and omits
transitive geometry/model/native dependencies. Fixture construction is represented
by its source, with no separate calibration or point digest. Concurrent mutation
is not excluded. Historical reports remain unchanged and cannot acquire new
execution provenance retroactively. Full V3 review is incomplete at C01; no
production KEEP/MIGRATE decision or audit-completion marker is added.

See [source-bound checks](evidence/phase2/registration-source-evidence-v3.json).
