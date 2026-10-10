# P16.1 capability passport profile v1

A passport is a signed **self-declared software capability statement**, not accreditation,
physical qualification, evidence truth, or motion authorization. This additive interface
changes none of the frozen v1/v2/v3 perception contracts. It exposes no actuation path.

## Decision and primary research

Requirements: bounded offline verification, portable bytes, public-key authentication,
external trust, expiry/revocation, retained negative evidence, no person or device identity.
Choose Python 3.9+ for the bounded parser and policy evaluator, with optional
`cryptography==50.0.2` for Ed25519. Its published Python floor includes 3.9.6 and its
Apache-2.0/BSD-3-Clause licensing is compatible with this GPL-3.0-only project.
This choice is based on inspectable bounded JSON handling and a maintained crypto API,
not a requirement to preserve the incumbent language. Rust would add a native build/ABI
boundary without changing these small message requirements; subprocess OpenSSL adds
filesystem/process races and timeout handling; handwritten crypto is excluded.

- [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html): deterministic serialization.
  This is an ASCII/safe-integer application subset, not a general JCS implementation.
- [DSSE protocol](https://github.com/secure-systems-lab/dsse/blob/master/protocol.md):
  sign pre-authentication encoding (PAE), including the payload type, not a bare digest.
- [Ed25519 API](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/):
  use the library verifier; missing/unsupported crypto fails closed.
- [TUF specification](https://theupdateframework.github.io/specification/): external trust,
  expiration and persisted version floors inform the local policy. This is not TUF.

## Wire contract

The [structural JSON schema](../../../contracts/interop/passport-v1.schema.json)
supports external tooling. Cross-field rules, lexical bounds, signatures and trust
checks below remain normative and require the full verifier.

Every input is exact UTF-8 bytes, at most 65536 bytes and depth 8; reject duplicate or
unknown fields, floats (including exponent notation), nonfinite values and boolean
integers. Root objects are closed. Identifiers match `[a-z0-9][a-z0-9._-]{0,63}`;
digests and raw public keys are 64 lowercase hex characters. No URLs, paths, free text,
biometric identifiers, precise hidden-person data, accreditation or restricted interfaces.

Payload fields: `version` (integer 1), `passport_id` (opaque statement identifier, never
a person/device identifier), `issuer` (software publisher alias), `subject_sha256`
(software artifact), `issued_at`, `expires_at` (UTC Unix seconds, safe integers),
`assurance` (literal `self_declared`), `motion_authority` (literal false), `capabilities`,
`evidence`. Lifetime is positive and at most 86400 seconds.

Capabilities: 1..3 unique objects with exactly `name` and `evidence_sha256` (1..16 unique
digests). Names are only `perception.direct.v3`, `presence.coarse.v2`,
`evidence.offline.v1`. Coarse v2 never becomes precise tracking. Evidence: 1..16 unique
objects with exactly `sha256`, `kind` (`synthetic`, `recorded`, `external_unverified`),
`outcome` (`passed`, `failed`, `unknown`). References must resolve, and all supplied
evidence must be referenced. Outcomes remain issuer assertions, including failed and
unknown entries; verification never fetches or qualifies evidence content.

Canonical payload: sort object keys lexically, no whitespace, unchanged array order,
plain decimal integers, JSON booleans and unescaped ASCII strings. Decode and validate
before canonicalizing. The signed payload bytes MUST already equal canonical bytes.
Outer envelope: exactly `payloadType`, `payload`, `signatures`. Type is
`application/vnd.aethron.capability-passport.v1+json`. Payload and signature use standard
padded canonical base64. Exactly one signature object, with `keyid` (SHA-256 of raw
32-byte Ed25519 public key) and `sig` (64-byte signature). Sign DSSE PAE:
`DSSEv1 SP len(type) SP type SP len(payload) SP payload`, lengths in decimal ASCII bytes.
This deliberately single-signer DSSE profile rejects extra signatures/algorithms.

## Externally provisioned policy and verification

Policy is separately provisioned through an authenticated local configuration channel;
an envelope cannot supply or extend it. It is bounded JSON with exactly `version` (1),
`revision` (positive safe integer), `issued_at`, `expires_at`, `keys`, `revoked_passports`,
`revoked_keys`, `revoked_evidence`. Policy lifetime is positive and at most 3600 seconds.
Revocation lists contain at most 256 unique identifiers/digests each. Keys: 1..16,
unique IDs and key material, each exactly `key_id`, `issuer`, `public_key`, `not_before`,
`expires_at`, `capabilities` (1..3 unique allowed names). Key ID must match key bytes.
All supplied key metadata is validated even for unselected keys.

`verify(envelope, policy, *, now_s, minimum_time_s, minimum_policy_revision, expected_subject_sha256)`
requires caller-trusted UTC time, a persisted policy revision floor and the exact
expected software artifact digest. The caller must persist the greatest accepted
policy revision and time across calls/restarts; this stateless function cannot detect
caller rollback. Pass the persisted time floor as `minimum_time_s`; time below it fails.
All intervals are half-open: issued/not-before <= now < expiry. The entire passport
interval must fit the selected key interval. Reject unknown/revoked keys, issuer or
capability scope mismatch, revoked passport or evidence, stale/future policy/passport,
policy rollback, mismatched subject, malformed wire and invalid signature. No network,
path reads, implicit clock, credentials, fallback algorithms, or controller imports.

Result is immutable and bounded: status `authenticated` or `rejected`, fixed reason,
canonical payload SHA-256 (authenticated only), policy revision and effective expiry
(authenticated only). `motion_authority` and `evidence_verified` are always false.
Every consumer must reverify at use time; a result is not an enduring authorization.
Offline revocation is known only through the supplied unexpired snapshot, not globally
current; missing freshness blocks verification, and shorter policy life may be chosen.

## Validation and limits

Use a published test-only signing seed; fixture keys are never deployment trust roots.
Retain tampered, expired, revoked, future, unknown-key, scope, authority and malformed
negative cases. Test actual Ed25519 signatures and a golden DSSE PAE vector, resource
limits before decoding, and seeded bounded parser mutation. Missing crypto must reject.
Default dependency-free installs retain the parser and fail closed on signature checks;
install the `passports` extra for Ed25519. Hosted checks exercise this extra separately.
No hardware, certification, live evidence, production, or complete revocation claim.
