# Signed local policy: fresh V3 review

Decision: **KEEP the loader implementation; RETRACT/CLARIFY stale technology,
resource and qualification prose.** This review covers `load_fleet_policy` and
its key-profile helper through `c7ee8fd2495d1dd1347b5347953ef37e942a26b9`.
The later admission transaction, persistent floors, rollout and fabric components
remain separate review subjects. Previous audit decisions are evidence inputs,
not completion of this review.

## Requirements and alternatives

Administrator-local Linux admission must bind seven closed JSON fields to signed
bytes and a locally pinned Ed25519 key, reject stale or downgraded configuration,
and return an immutable value or fixed error. Policy bytes are capped at 2048;
key bytes at 1024. The API has no network, installation or vehicle authority.
The caller owns UTC trust, rollback floors and protected file/executable paths.
No throughput target, target hardware budget or real-time deadline is supplied.

Fresh source review on 2026-10-10 supports this comparison. The assessment is an
engineering inference about the complete boundary, not an unmeasured speed ranking.

| Candidate | Decisive property and assessment |
| --- | --- |
| Python + shared OpenSSL process | [OpenSSL pkeyutl](https://docs.openssl.org/3.5/man1/openssl-pkeyutl/) supports Ed25519 and other algorithms. Fleet must pin the algorithm before invoking it. Maintained JSON hooks preserve duplicates/numeric types; bounded field comparisons and an immutable result complete this small boundary. Keep one upstream-owned bundle verifier. |
| Python cryptography native binding | [Typed key deserialization](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/serialization/) can identify Ed25519 keys and supports in-process native crypto. It could remove verifier process startup in an upstream migration; using it only for fleet key parsing would add a general ASN.1 dependency while retaining the current subprocess. No deadline demonstrates that this change wins here. |
| Rust ed25519-dalek | The [typed verification API](https://docs.rs/ed25519-dalek/latest/ed25519_dalek/) is a credible native replacement with a binding. File snapshot, JSON and fixed-error parity remain necessary. Rust is not restricted to standalone daemons; duplicating the peer-owned bundle verifier is not part of this consumer's implementation. |
| Java EdEC APIs | [EdECPublicKey](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/interfaces/EdECPublicKey.html) exposes curve information. A Java-hosted library could enforce Ed25519 without an application-owned ASN.1 parser; it would still need exact input bounds and immutable file pinning. No Java hosting requirement or full parity measurement exists here. |
| Erlang/Elixir OTP crypto | [OTP crypto](https://www.erlang.org/doc/apps/crypto/crypto.html) exposes signature verification with explicit algorithm selection. Supervision benefits a distributed service; no actor/service requirement exists in this synchronous local API. A service would need bounded authenticated messages and cancellation semantics. |
| Node crypto and Go Ed25519 | Both have native or standard-library verification APIs, as recorded in the [V2 comparison](fleet-policy-technology-audit-v2.md). They remain credible; neither language inherently requires a separate process. Exact JSON token handling, key profiles and caller integration still need full parity checks before substitution. |

KEEP rests on maintained parsing, bounded checks and composition with one native
verifier. It gives no preference for installed tooling or sunk implementation
cost. No alternative has an evidenced material end-to-end win under the supplied
constraints. Independent service hosting, required verifier latency, key lifecycle
requirements or a new upstream crypto interface would reopen the decision.

## Rechecked behavior and corrections

The key helper matches the fixed Ed25519 encoding in
[RFC 8410](https://www.rfc-editor.org/rfc/rfc8410.html): algorithm parameters are
absent and the public key occupies 32 bytes. The helper is an encoding allowlist,
not a general certificate parser or a cryptographic key-validity proof.
Cryptographic verification remains OpenSSL's responsibility.

Fresh execution passed all 17 policy tests, including real signatures, a wrong
root, payload mutation after verification, key-path replacement, malformed PEM/
DER and same-length alternate-algorithm rejection. The latter uses a synthetic
RSA root; it does not demonstrate a forgery under Ed25519. The complete focused
policy/admission/plan/claim regression run passed 58 tests. Historical pre-fix
negative results remain in the V2 evidence; no new production defect was found
in this loader during the current review.

The main contract incorrectly implied no process boundary and that Go/Rust
required IPC. Those claims are corrected. The obsolete implementation checklist
is replaced with tested status. The existing key profile is now stated in the
main contract rather than discoverable only in the previous audit.

Resource review confirms a distinction between the policy parser and its bundle
dependency: the latter accepts a 2 MiB manifest, up to 8192 members and up to
512 MiB per payload. Inventory traversal is not covered by the OpenSSL timeout.
There is no whole-operation deadline or network-ingress claim. Expiry is checked
against the caller's supplied timestamp, not a live clock in this primitive.

[Fresh evidence](../verification/fleet-policy-review-v3.json) binds current source
and test bytes, records test counts and preserves the earlier negative evidence.
No comparative cryptographic benchmark, formal proof, hardware test or complete
alternative-language implementation was run. Those omissions are not evidence
against alternative technologies.

Reproduce the focused run from the lane environment with its installed test
dependencies:

```sh
PYTHONPATH=integrations/edge:build/fleet-linux-deps:tests/integration python3 -m unittest test_fleet_policy test_fleet_admission test_fleet_plan test_fleet_claim -v
```

## Integration limits and cursor

Configuration provenance is not truth of a signed statement, platform readiness,
operator authority, confidentiality or a deployment permit. Consumers must not
translate these fields into scene evidence or actuation. P17/P18 transport,
classification separation, cryptographic compliance and physical timing are not
certified by this loader. No competing peer module or unsafe capability is added.
Insufficient information for tactical deployment.

Health and this loader have fresh V3 component decisions. The next earliest
component is persistent version/time floors. No full-lane completion marker is
appropriate while later components remain unreviewed.
