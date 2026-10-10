# Probe source provenance review — 2026-10-10

Baseline `d01e21e84ae99273e3d0f1d3486c4a5943cb61a2`. The preceding delivery bridge
was verified. The current policy, declaration/artifact/campaign/reference/bundle
contracts, probe sources and Python comparison drivers were reviewed; seventeen
earlier declaration, artifact, campaign and measurement control methods passed.
No change to production admission or physical qualification gates is made here.

## Historical source verification

All 185 declared source bindings across eighteen retained JSON records match the
source bytes in the commit that last published that report version. The inventory
in [probe-provenance-v3.json](probe-provenance-v3.json) supplies immutable commit and
report-byte locators. It includes nested source manifests. Retrieve the exact
report and each declared source using `git show COMMIT:PATH`, then recompute SHA-256
of the source bytes. Publication means a local repository commit, not proof of
GitHub availability, execution time or authenticated generation. Reports without
source maps are not included in the count, and matching listed sources does not
prove that the list is complete.

Historical result files remain byte-for-byte unchanged. A source match is not a
fresh test pass or evidence that the code ran. Older comparison, timing and tracing
limitations documented in [review-v3.md](review-v3.md) remain applicable. In
particular, Node's four ingress mismatches remain negative evidence, and Java's
shared Python semantic oracle is not independent Java semantic validation.

## Current output correction

**FIX the two Node probe report emitters.** `ingress-probe.mjs` omitted its source
and vector bindings. `hash-probe.mjs` omitted its source binding although a retained
result had that field added externally. Fresh stdout could not reproduce those
provenance fields without a separate editing step. Both emitters now include
`audit_policy_version: 3` and `source_sha256` directly. Ingress hashes the same raw
vector buffer it parses; each probe hashes its own on-disk module. Source reads and
hashes occur outside the hash probe's measured copy/hash loop.

Two explicit integration methods independently recompute hashes in Python, check
exact source-map membership, retain all four ingress mismatches, and check known
hash vectors and alias/ownership behavior. RED had two assertion failures and no
errors/skips. The tests remain outside ordinary Python-only test discovery and run
explicitly in the existing optional ingress audit job. That job selects Node
22.23.2 and retains the emitted ingress JSON alongside its other audit artifacts.
Workflow existence is not a hosted pass.

## Technology decision

Requirements are finite Node token/Buffer experiments with auditable emitted JSON,
exact vector-byte identity and no physical or timing acceptance claim. Node is the
subject of the experiment: replacing JSON parsing or Buffer operations with
another runtime would test a different candidate. Native Node crypto and file
reads attach local byte fingerprints without a child hashing command. Python
hashlib supplies an independent host check. Git native object reading preserves
historical bytes without a checkout or generated reconstruction.

**KEEP Node for these probes and Python for the independent check; FIX emission.**
C#/F# `SHA256.HashData`, Rust SHA-2, and external `sha256sum` are credible digest
hosts, but none removes the requirement to execute the Node behavior under test.
A separate attestation builder would be relevant for authenticated execution
provenance; these local fingerprints do not meet that different requirement.
No runtime is selected for familiarity, installation convenience or diversity.
No measured performance ranking is inferred.

Primary sources: [Node crypto](https://nodejs.org/api/crypto.html),
[Node file reads](https://nodejs.org/api/fs.html),
[.NET SHA-256](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.sha256.hashdata?view=net-9.0),
and [Git object batch reads](https://git-scm.com/docs/git-cat-file).
These support mechanism descriptions; selection is this review's analysis.

The source checkout must remain stable while a probe runs. Reading its module
file does not attest the already-loaded executable bytes if that file changes
concurrently. The manifests omit Node/OpenSSL binaries, environment and OS state;
they are not signatures, supply-chain attestations or cryptographic certification.
Test subprocess timeouts do not bound process creation, output capture has no
independent byte ceiling, and the child/source fixtures are trusted. No sensor,
actuator, device, field or hardware qualification follows from these checks.

## Exact-head hosted failure retained

The core job at baseline `d01e21e` failed the immutable-tree link check because
`campaign-references-v1.md` split a link destination after the opening parenthesis.
The checker interpreted the newline as part of the path. The destination is now
on one line; the referenced audit file and its evidence are unchanged. The failed
[job log](https://github.com/Nima0101/aethron/actions/runs/38045555721/job/114194246579)
is retained as negative evidence. Targeted working-file link closure does not
replace the post-commit immutable-tree check or remaining required hosted checks.
