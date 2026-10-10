# P16 evidence content binding v1

This additive adapter binds local evidence bytes to an authenticated passport v1.
It does not interpret reports, change signed outcomes, grant motion authority, assert
physical qualification, or implement another lane's qualification/data registry.

## Requirements-driven technology decision

Inputs are already in memory, at most 16 immutable byte strings of at most 65536 bytes
each (1 MiB aggregate); output is small immutable metadata. No filesystem, network,
stream iteration, hidden clock, subprocess, or new trust source is needed. Linux,
macOS and Windows consumers must share the existing versioned byte contract.

[In-toto statements](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md)
bind immutable artifacts by digest, which motivates checking the actual bytes separately
from authenticating assertions. This adapter is not an in-toto verifier.
[Python hashlib](https://docs.python.org/3/library/hashlib.html) and
[Go crypto/sha256](https://pkg.go.dev/crypto/sha256) both provide maintained SHA-256
implementations. An FFI boundary does not inherently require copying: a suitable native
API can borrow a stable buffer. Runtime choice must preserve the immutable snapshot
across authentication and hashing. The [V3 evidence review](../../engineering/reviews/p16-evidence-v3.md)
compares native and managed alternatives and keeps Python with native-backed SHA-256
for this bounded offline contract. Dependency convenience alone is not the rationale.
There is no hard-real-time or hardware-performance claim; implementation language remains
replaceable by a conformant adapter if measured deployment requirements justify it.

## API and bounds

`aethron.passport_evidence.verify_evidence(envelope, policy, evidence, *, now_s,
minimum_time_s, minimum_policy_revision, expected_subject_sha256)` reauthenticates the
passport on every call using all v1 checks and mandatory caller-trusted floors. Evidence
must be an exact tuple containing 1..16 exact `bytes`, each 0..65536 bytes. Bytearrays,
views, paths, iterators, lists and subclasses are rejected; the snapshot cannot mutate
while signature or content hashing runs. Validate all sizes/types before authentication
or hashing. An invalid/untrusted/expired/revoked passport prevents content hashing.

Compute each supplied SHA-256, rejecting duplicate content digests. Require exact set
identity with every signed evidence reference: missing, substituted and extra blobs all
reject. Ordering of supplied blobs does not matter. Empty bytes are permitted only if
the signed reference names their exact digest; empty evidence tuples are rejected.
The signed `failed` and `unknown` outcomes must remain present in the result.

Result: immutable `EvidenceBindingResult`, with status `bound` or `rejected`, a fixed
reason, optional passport digest/revision/effective expiry (success only), and an immutable
tuple of `EvidenceReference(sha256, kind, outcome)` in signed order (success only).
`motion_authority` and `evidence_verified` are always false, including in dataclass
serialization. `bound` means bytes match an authenticated assertion, not that its content,
licensing, outcome, scientific merit or physical validity is established. No raw evidence
bytes, caller identifiers, paths or exception details appear in the result.
Digest metadata is not anonymization or encryption: identical artifacts have identical
digests, and guessed artifacts can be hashed for comparison. The caller owns appropriate
handling of both input bytes and returned metadata. This API promises no secure memory
erasure or removal of caller-held references.

Reverify at use time. The caller still owns trustworthy policy provisioning, persisted
time/revision floors and the expected software digest; accepting an old result object is
not a substitute. No existing passport profile bytes or frozen thresholds are modified.

## Focused acceptance

Exercise actual signatures; known SHA-256 vectors; failed and unknown evidence retention;
input permutation; missing/extra/substituted/duplicate content; exact and exceeded resource
bounds; non-bytes/custom containers; missing crypto; expiry/revocation; and invalid
passports rejecting before any content hash call. All success/failure results deny motion
and evidence qualification. Hosted tests use the optional passport crypto environment.
