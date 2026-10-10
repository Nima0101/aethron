# Signed fleet policy: retrospective audit and key profile v2

Audit policy version: **2**. Decision: **KEEP Python admission with the shared
native OpenSSL verifier; repair the fleet trust-root boundary before advancing
the audit.** This reviews `load_fleet_policy`, introduced in `6a22dd2`, through
`746b1e3a92f13599261e06408f4d3c1b8422dede`. It supersedes the technology rationale
in `fleet-policy-v1.md`, not the frozen policy JSON fields or timing thresholds.
The admission/floor transaction, rollout journal and plan/claim adapters have
separate audit entries. P11 forward work remains paused.

## Constraints and alternatives

This is administrator-local, offline admission of a policy of at most 2048 bytes,
with exact integer types, closed fields, a pinned trust root, authenticated
payload bytes, expiry and a supplied rollback floor. It must return immutable
configuration or a fixed error; it grants no installation or vehicle authority.
Linux deployment is required. No realtime deadline, throughput target, OEM SDK,
network service or independent policy daemon is required. The caller supplies
trusted time and protects the bundle/key directories. The shared verifier is
owned upstream; fleet consumes that interface without implementing a competing
signature or bundle verifier.

The current verifier has broader bundle-size limits than this policy parser and
may hash other signed payloads. This API is not a bounded network-ingress service.
The later snapshot adapter has its own limits and remains separately audited.

Current primary sources were reviewed on 2026-10-10. Assessments below are design
inferences, not unmeasured runtime rankings. Tool installation and rewrite cost
were not selection criteria.

| Technology | Relevant evidence | Component decision |
| --- | --- | --- |
| Python standard-library parsing + OpenSSL process | OpenSSL `pkeyutl -rawin` supports multiple algorithms and infers hashing from the key for several of them. A 64-byte signature does not select Ed25519. [OpenSSL](https://docs.openssl.org/3.5/man1/openssl-pkeyutl/) | Keep native crypto outside the application process and preserve the existing verifier interface, but bind the accepted algorithm and key bytes explicitly. Shared-verifier process timeout/error behavior remains in force. |
| Python `cryptography` typed keys | PEM deserialization returns typed public-key objects, including Ed25519; the library provides native cryptographic operations. [Serialization](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/serialization/) | Credible in-process migration. It could avoid command startup if the upstream verifier migrated, but adding it only to fleet while keeping the shared verifier would duplicate key-decoder dependencies. A general PEM/ASN.1 object model is unnecessary for the one exact public-key shape used here. No cryptographic throughput requirement establishes a win from replacing process isolation. |
| Rust with ed25519-dalek | Typed signing/verifying keys and Ed25519 verification APIs are available. [ed25519-dalek](https://docs.rs/ed25519-dalek/latest/ed25519_dalek/) | Credible native core with static types. It would need a binding and exact bundle/parser parity, or an upstream-produced replacement interface. The fleet consumer should not create a second competing implementation of shared bundle verification. No claim that Rust requires a separate process. |
| Java with EdEC key interfaces | The standard API exposes Edwards-curve public-key type information and parameters. [EdECPublicKey](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/interfaces/EdECPublicKey.html) | A Java policy service could check key parameters before verification. Typed keys do not by themselves establish file bounds, immutable pinning, policy integer-token semantics or trusted time. A JVM service/binding adds a boundary without a requirement for Java hosting here. |
| JavaScript/TypeScript with Node crypto | `KeyObject.asymmetricKeyType` distinguishes Ed25519 from RSA and other key types. [Node crypto](https://nodejs.org/api/crypto.html#keyobjectasymmetrickeytype) | A viable native-crypto API, but policy JSON still needs duplicate and numeric-token preservation before object validation, as demonstrated by the preceding health audit. No Node signature-performance claim is made. |
| Erlang/Elixir with OTP crypto | OTP exposes signature verification operations with algorithm/key selection. [OTP crypto](https://www.erlang.org/doc/apps/crypto/crypto.html) | Appropriate for an independently supervised distributed admission service. This local function has no mailbox, actor-failure or distributed-runtime requirement; such a service would need a new bounded authenticated request/reply contract. |
| TUF client and metadata model | TUF has distinct signature, expiry and rollback checks and role metadata. [TUF specification](https://theupdateframework.github.io/specification/latest/) | Relevant secure-update architecture, not a drop-in implementation of this existing offline bundle. Role/key-rotation migration belongs to an explicit versioned protocol change, not a claim of compliance from a parser replacement. |

The positive reason to KEEP is the small policy boundary: strict parsing through
maintained hooks, explicit bounded comparisons and immutable results, composed
with one shared verifier. Native cryptographic verification is already delegated;
rewriting seven-field admission adds no demonstrated required capability. The
boundary defect below must be corrected irrespective of language. A future
independent service, required in-process verification latency, or upstream
versioned crypto interface should reopen the decision; none is silently assumed.

## Root cause and executable negative evidence

The earlier loader passed the supplied public-key path directly to the shared
verifier. It checked neither its key algorithm nor its bytes before the verifier
opened it. The shared verifier checks signature length but OpenSSL can also
verify a 64-byte RSA-512 signature. A real, ephemeral RSA test fixture therefore
loaded successfully before the fix, violating the fleet Ed25519 profile.
This requires supplying an RSA trust root; it is **not** a demonstrated forgery
under a pinned Ed25519 key. A second regression replaced the original key path at
the verifier boundary; before the fix, admission failed despite the earlier key
being the intended pin. These tests establish the selection and reread behavior.

## Corrected fleet key profile

The loader now reads a regular, non-symlink key file of at most 1024 bytes. Its
content must be a single `PUBLIC KEY` PEM block, containing canonical Base64 of
exactly 44 DER bytes: the 12-byte Ed25519 SubjectPublicKeyInfo prefix
`302a300506032b6570032100`, followed by a 32-byte public key. The profile rejects
other algorithms, ASN.1 parameters, different lengths, nonzero unused-bit counts,
trailing DER, noncanonical Base64 padding, extra PEM blocks and surrounding text.
LF and CRLF body line wrapping are accepted; the verifier receives normalized PEM.

This is a fixed wire-shape allowlist, **not a general ASN.1 parser or a signature
implementation**. The Ed25519 OID, absent parameters and public-key encoding follow
[RFC 8410 sections 3–4 and 10.1](https://www.rfc-editor.org/rfc/rfc8410.html).
Cryptographic key/signature validity remains the native verifier's responsibility.
The public-key bytes are copied into a private temporary directory and that path
is passed to the verifier, so replacing the original path cannot change the
selected key after admission. The copy is removed before a policy is returned.
There is no additional process, native dependency, network call or secret-key
handling. Directory protection and trusted executable selection remain deployment
assumptions; the temporary copy is not a defense against a malicious same-user host.

This versioned key-profile correction intentionally rejects previously accepted
non-Ed25519 or ambiguous key files. Standard OpenSSL Ed25519 public PEMs preserve
compatibility. Existing policy fields, expiry/floor values and artifact hashing
are unchanged. A nonconforming key cannot request a weaker fallback.

## Verification and remaining limits

[Focused evidence](../verification/fleet-policy-technology-audit-v2.json) records
17 policy tests and the 48-test policy/admission/plan/claim regression run. Four
new test methods cover the real alternate-algorithm signature, original-path
replacement, 13 malformed/ambiguous key cases, regular-file restrictions and PEM
line wrapping. Rejection before shared verification is checked for malformed keys.
The existing real OpenSSL signatures, wrong roots, tampered payloads, time/version
bounds and post-verification payload replacement remain covered. No test key is
used outside temporary synthetic fixtures.

No blanket language-speed or hardware claim follows from these tests. The audit
does not establish TUF compliance, key rotation/revocation, algorithm agility,
secure-time provenance, durability or production deployment readiness. Later
components and the upstream verifier retain their own audit obligations.
