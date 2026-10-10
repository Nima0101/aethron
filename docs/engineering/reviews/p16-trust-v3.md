# P16 signature and trust review v3

Baseline: `6bf8f6a7762b5a06d128f841773cc7587f3c4846`. Reviewed 2026-10-10.
Decision: **KEEP bounded offline Python/native verification; FIX test evidence and
CLARIFY enrollment and technology claims**. No production algorithm or wire change.
This record covers signatures, trust metadata, expiry and revocation, not the later
evidence-binding, task, federation, inbox or unimplemented P17/P18 components.

## Constraints and current alternatives

This is a stateless, offline software-statement verifier: exact immutable bytes,
64 KiB input bounds, one Ed25519 signature, at most 16 provisioned publisher keys,
three lists of at most 256 revocations, caller-owned time/revision floors and artifact
pin. It neither generates keys nor discovers trust. There is no throughput SLA,
embedded target runtime, hard deadline, encrypted channel or classified-data boundary.
The requirement is explicit rejection and portable signed-byte behavior on the
supported desktop operating systems. No signature grants motion or evidence authority.

| Candidate | Decisive properties and limits |
|---|---|
| Python plus cryptography/OpenSSL | [Pinned API](https://cryptography.io/en/50.0.2/hazmat/primitives/asymmetric/ed25519/) accepts raw public keys and reports invalid signatures or unsupported algorithms. Bounded policy checks stay separate from native cryptographic arithmetic. Current tests exercise both rejection paths. |
| Rust plus ed25519-dalek | [Verifier API](https://docs.rs/ed25519-dalek/latest/ed25519_dalek/struct.VerifyingKey.html) offers weak-key inspection and strict verification. Strong candidate for a native runtime or a stricter key profile. Its acceptance rules must be evaluated explicitly; sharing the Ed25519 name does not prove byte-level equivalence. No native target or measured bottleneck currently requires it. |
| Java/Kotlin plus JCA | [Standard algorithm names](https://docs.oracle.com/en/java/javase/25/docs/specs/security/standard-names.html) include Ed25519. Provider-backed verification and typed policy records are credible. A provider's availability and failure mapping require explicit checks; algorithm registration does not implement policy freshness or revocation. |
| Node.js crypto | [Crypto API](https://nodejs.org/api/crypto.html) supports Ed25519 verification with a null algorithm. An executable six-case primitive comparison agrees with the Python backend. Plain JSON parsing loses duplicate keys and number lexemes, so native signature support alone does not replace admission. |
| C or a safe language binding to libsodium | [Detached verification](https://doc.libsodium.org/public-key_cryptography/public-key_signatures) is a credible small native boundary. The multipart API uses Ed25519ph and is not a transparent substitution for this profile's Ed25519. A complete bounded parser/policy evaluator remains required. |

KEEP is limited to this offline contract: explicit lexical hooks plus a narrow native
verifier satisfy the required rejection behavior without custom cryptographic code.
The comparisons establish viable alternatives, not a universal language ranking.
No measured or requirement-derived advantage currently establishes a winning migration.
Rewrite cost and installed tools are not selection criteria. A native deployment
constraint, stricter cryptographic profile or measured bottleneck reopens this decision;
this result does not choose a runtime for physical I/O or claim real-time performance.

## Fresh findings and executable evidence

The prior test named "validates all keys" did not include a malformed unselected key.
It also lacked direct tests of the backend's UnsupportedAlgorithm path and the
effective-expiry minimum when policy expires before the statement. Four new methods
cover those gaps and revocation after a successful call. Rejection assertions now
require both revision and expiry metadata to be absent as well as the payload digest.
These tests passed on the existing verifier; no production defect was demonstrated.

The [mutation evidence](p16-trust-v3-mutations.json) binds exact source hashes. Run:

```sh
python -m unittest tests.test_passports -v
python scripts/passport_trust_review.py
python scripts/passport_technology_probe.py
```

The first command runs 24 tests. The second removes four guards independently in
isolated in-memory modules: unselected-key validation, effective-expiry minimum,
evidence revocation, and rejection-metadata clearing. All four mutations are detected
by eight expected assertion failures, with zero errors or skips. Production files are
never rewritten. These are negative-test sensitivity checks, not observed production
failures. The third is the historical V2 probe rerun as supporting V3 evidence: six
primitive comparisons and five lexical negatives; its local timing sample is not a
full competitor benchmark, timing guarantee or cryptographic validation certificate.

The focused passport/evidence/schema/task/bundle/federation/inbox suite passes 68
tests using `PYTHONPATH=tests:. python -m unittest test_passports
test_passport_evidence test_passport_schemas test_interop_tasks test_interop_bundles
test_interop_federation test_interop_inbox`. An initial invocation without that test
import path produced three module-import errors; it did not demonstrate a production
failure. Ruff, formatting and the production verifier's Bandit scan pass.

Documentation now distinguishes metadata validation from trusted key enrollment and
removes the old build/ABI-cost rationale. The backend verifies the selected signature;
the component does not mathematically validate every unselected public key, prove key
ownership, authenticate the policy transport, persist rollback floors or discover live
revocations. Consumers must supply authenticated policy/time/floors and reverify at use.
MLS, CNSA, five-nines, hardware and tactical qualification remain unestablished.

Next earliest component: P16 evidence byte binding. V3 review remains incomplete.
