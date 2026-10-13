# C03 report source fingerprints — V3, partial

Decision: **FIX report provenance.** The geometry comparison reported NumPy's
version and aggregate results without identifying exact source files. New
reports hash the harness and the actual imported geometry module's on-disk file
with SHA-256. Source selection follows the import location, including an
installed package. Logical labels omit absolute paths. Missing source files
prevent report emission. Hashing occurs after admission checks, before measured
batches, and outside traced allocation passes.

The change is limited to offline diagnostic report assembly over small trusted
local files. Python [hashlib](https://docs.python.org/3.13/library/hashlib.html)
provides SHA-256 over bytes in process. Node
[crypto](https://nodejs.org/api/crypto.html) also exposes hashes, but moving these
already accessible bytes into a separate runtime adds an exchange without
improving fingerprint semantics. This narrow reporting choice adds no dependency
and does not settle the production geometry technology reassessment or claim a
performance advantage.

Two new methods use inert cameras and substitute clocks/tracing, exercising
report assembly without benchmarking geometry algorithms. They verify exact
source selection using a temporary installed-module path and a known SHA-256
vector, omission of the private path, and missing-source rejection. Before the
change: two assertion failures and no execution errors. After: all nine focused
methods pass. Ruff/format pass; two LOW Bandit findings match the prior source.
All existing functions/classes and `main` outside the report assignment have
unchanged ASTs, including the algorithms, fixture generation and measurement loop.

This manifest fingerprints on-disk bytes, not loaded executable code. Imports
precede hashing; mutation during execution is not excluded. Dependencies and
native libraries are not fully identified. Fixture-generation code is included
through the harness hash, but no separate serialized fixture digest is claimed.
Reports remain unauthenticated, and the existing warm-up-only parity limitation
is unchanged. Historical measurements are unmodified and not retrospectively
qualified. Full V3 review remains incomplete at C01; no production KEEP/MIGRATE
or audit-completion claim is added.

See [source-bound checks](evidence/phase2/geometry-source-evidence-v3.json).
