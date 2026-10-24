# Locked offline consumer correction

Hosted Linux and Windows runs failed because offline `npm install <archive>`
resolved dependency metadata that `npm ci` had not cached. Retain that failure.
The production-service harness has the same assumption. Fix both consumers with
one versioned npm lock-v3 projection, not a network fallback or a warm-cache claim.

Use a build/test-only ECMAScript adapter: npm already requires Node, its JSON lock
is the versioned boundary, and Node SHA-512 binds the exact local archive. Compare
Python stdlib JSON/hashlib (viable harness integration but introduces Python into
Node-only package checks) and Rust/Serde (viable strict data handling but adds a
native executable/toolchain without a demonstrated throughput requirement).
Keep Python for existing HTTP-service orchestration; call the shared local adapter.
This is interoperability-driven selection, not a benchmark or incumbent preference.

1. Four missing-helper regressions precede implementation.
2. Project the committed runtime dependency lock plus local archive integrity into
   an external consumer manifest/lock. `npm ci --offline --ignore-scripts` verifies
   the graph. No registry metadata or lifecycle scripts are required.
3. Prove install/uninstall/locked reinstall using a fresh tarball-only cache with
   no registry packuments; preserve type and no-eval runtime checks.
4. Reuse the adapter in the service harness, run controlled failures and actual
   bounded loopback integration; format the three lane-owned CI failures.

No clean clone, full matrix, privileged installation or production qualification.
Search work resumes after this earlier packaging correction is committed.
