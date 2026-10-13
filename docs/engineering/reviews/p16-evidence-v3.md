# P16 evidence binding review v3

Baseline: `be2b0f00b855b2e77844f12ac151fd8f1f1158d3`. Reviewed 2026-10-10.
Decision: **KEEP bounded Python/native hashing; CLARIFY memory and privacy claims;
FIX negative-test coverage**. No production or versioned wire change was needed.

## Deployment constraints and current alternatives

The synchronous offline API accepts 1..16 already resident immutable blobs, each
0..65536 bytes, and an immutable envelope/policy. It must authenticate first, bind the
complete digest set, preserve signed failed/unknown outcomes, and return metadata only.
It performs no content interpretation, file or network I/O, sensor correlation, control,
streaming, persistent state or enrollment. It has no physical target or deadline claim.
The one-MiB bound covers input content, not interpreter RSS or all native allocations.

| Candidate | Evidence and decisive tradeoff |
|---|---|
| Python/hashlib | [hashlib](https://docs.python.org/3/library/hashlib.html) hashes bytes using native implementations; large hash calls can release the GIL. Exact `bytes` and tuple admission are therefore meaningful immutable-snapshot controls, not a reliance on single-threaded execution. |
| Rust/sha2 | [RustCrypto SHA-2](https://docs.rs/sha2/latest/sha2/) provides one-shot/incremental APIs and native backends. Owned immutable input and safe borrowing are credible for a native implementation. This is a real alternative; FFI need not copy. A new native boundary has no demonstrated benefit for the current bounded metadata operation. |
| C#/.NET | [SHA256.HashData](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.sha256.hashdata?view=net-10.0) accepts spans and supports caller-provided digest storage. Buffer ownership must prevent concurrent writes; a read-only view alone does not promise immutable backing storage. This could suit a .NET consumer without changing the byte contract. |
| Erlang/Elixir with OTP crypto | [crypto:hash/2](https://www.erlang.org/doc/apps/crypto/crypto.html#hash/2) accepts full message data and returns a binary digest. [Binary handling](https://www.erlang.org/doc/system/binaryhandling.html) offers immutable data semantics and reference-counted binary handling. A credible choice for a BEAM-hosted consumer; scheduler/process distribution does not itself improve this stateless offline call. |
| Node.js native crypto | The existing independent primitive probe checks the same SHA-256 result. Mutable Buffer inputs require an ownership discipline across authentication and hashing. That probe is not a full binding implementation or comparative throughput qualification. |

KEEP rests on exact immutable snapshots, native hashing and an executable small
rejection surface. No manual cryptographic arithmetic or joined content buffer is
needed. None of the reviewed alternatives establishes a material improvement against
these particular deployment constraints; installation familiarity and rewrite cost
are not reasons to keep Python. A different host runtime, memory budget or measured
bottleneck requires a new comparison. This decision does not select P18 processing
technology or imply target-hardware performance.

## Findings and checks

The old contract incorrectly generalized that process/FFI boundaries add input copies.
The corrected text permits native borrowing with stable ownership. It now distinguishes
returned digest metadata from anonymization, encryption and secure memory erasure.
Matching public or guessable artifacts can correlate digests; content binding is not
permission to publish them. The caller retains responsibility for input/metadata handling.

Production inspection confirms preflight before authentication/hashing, fresh public
passport verification per call, and complete set equality including negative evidence.
Three added tests check tampered signatures before content hashing, late backend failure
without partial metadata, and a blob whose claims conflict with the signed failed
outcome. Blob claims never grant authority or change signed outcomes. Rejection helpers
also check absent revision/expiry. These tests pass on existing production code;
no new production bug or failing production regression is claimed.

Reproduce focused checks with the optional passport backend installed:

```sh
python -m unittest discover -s tests -p test_passport_evidence.py -v
python -m unittest discover -s tests -p 'test_passport*.py'
python -m unittest discover -s tests -p 'test_interop*.py'
```

Source-bound results are in [the review evidence](p16-evidence-v3-results.json).
Tests cover the one-MiB maximum, empty blobs, missing/extra/duplicate substitutions,
all-before-hash preflight, signature/time/revocation rejection and fixed error output.
They do not establish FIPS/CNSA, MLS, content truth, availability or physical qualification.

Next earliest review: P16 schemas, vectors, conformance and tooling. V3 remains open.
