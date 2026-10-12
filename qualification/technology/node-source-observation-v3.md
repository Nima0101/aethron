# Node probe source observations

Baseline: `e6f458cfeec48576e67e0fbc1e404f74774d4268`. The P4/P15 review
returns to the Node primitive and ingress experiments after the declaration,
artifact, campaign, reference, bundle and Python reporting boundaries. This
correction does not complete the lane review or product acceptance.

Both probes previously hashed their module file only after the experiment.
Ingress retained the initial vector bytes but did not check the final file.
Consequently changed module files, changed vectors and even removed vectors
could accompany a successful report. Earlier reports remain unchanged and are
observations of file contents, not proof of executed code.

The probes now retain initial module digests before the workload. Ingress also
hashes the exact initial vector buffer before parsing. Final module/vector reads
must match before JSON output is constructed. A changed digest throws
`probe_sources_changed`; an unreadable file propagates the Node filesystem error.
Neither path emits report JSON. Filesystem diagnostics may include the trusted
checkout path; these tools are not a private untrusted-input service.

Successful reports retain the initial digests and add `source_observation` equal
to `equal_before_and_after_workload`. File operations are outside the hash timing
loop. The ingress corpus still has four duplicate-key mismatches; a successful
probe process does not mean its parser has qualification parity.

## Technology decision

These are offline source-checkout experiments observing Node Number/JSON,
Buffer ownership and native SHA-256 behavior. They use 18 trusted ingress vectors
or ten repetitions over four 1 MiB buffers. There is no service, device SDK,
standalone product distribution or hard deadline. The requirement is to bind
observed files around this particular runtime's experiment without changing its
timed workload or hiding negative evidence.

| Candidate | Decisive property |
|---|---|
| Node JavaScript with built-in file reads and crypto | Direct access to the measured runtime and its workload boundaries; native byte hashing and explicit comparison satisfy the file-observation requirement. |
| F# or C#/.NET coordinator | Byte/stream SHA-256 is available. An external coordinator requires a lifecycle handshake to surround the Node experiment; replacing the experiment itself would measure different JSON and buffer semantics. |
| Git object inventory | Supplies immutable publication identities. A committed object is not an observation of the working file during the experiment. |
| Nix derivation | Suitable for controlled build inputs and execution. A hermetic execution protocol is a separate requirement; two file observations cannot claim its properties. |

**KEEP JavaScript on Node for these experiments; FIX source observations.** This
is a choice of experimental subject and direct workload control, not familiarity,
installation convenience, rewrite cost or a claim that Node is the best production
validator. In particular the retained duplicate failures do not justify migrating
production admission to this parser. Reopen the orchestration choice for hermetic
builds, independent attestation or an actual target-resource requirement.

Official mechanism sources:
[Node file reads](https://nodejs.org/api/fs.html#fsreadfilesyncpath-options),
[Node hashing](https://nodejs.org/api/crypto.html#cryptocreatehashalgorithm-options),
[.NET byte/stream hashing](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.sha256.hashdata?view=net-9.0),
[Git tree inventory](https://git-scm.com/docs/git-ls-tree), and
[Nix derivations](https://nix.dev/manual/nix/2.34/language/derivations.html).
The suitability decision is this review's analysis.

## Executable evidence and limits

Five test methods run actual Node subprocesses. Three methods alter or remove
only disposable module/vector copies during execution, using a timing or parsing
hook; each verifies that its file mutation actually occurred. Stable controls
independently recompute source hashes, check known SHA-256 vectors and Buffer
ownership, and retain all four ingress failures. The RED run had six assertion
failures and zero execution errors: two changed modules, changed/removed vectors
and two missing-metadata controls. Module removal already stopped the old probes.
After correction all five methods pass. The hosted audit already invokes this
test module; no workflow expansion is needed.

Fresh reports, source bindings and static checks are retained in
[node-source-observation-v3.json](node-source-observation-v3.json). The recorded
timings are descriptive shared-host observations, not a speed ranking or deadline.

Reads cover fixed trusted files in full, with no added file-size or wall-clock
limit. Two non-atomic observations cannot detect transient reverted edits, stale
loaded code, unlisted dependencies, instrumentation or post-check changes.
Neither the digests nor these regressions authenticate execution, establish
cryptographic certification, or qualify hardware or an installed customer product.
Insufficient information for tactical deployment.
