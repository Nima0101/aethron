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
The current [V3 parser review](../../engineering/reviews/p16-parser-v3.md) and
[V3 trust review](../../engineering/reviews/p16-trust-v3.md) reassess this selection
against native and managed alternatives. Build convenience or migration cost does not
justify the choice. Cryptographic arithmetic remains in the maintained backend;
handwritten crypto is excluded.

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
integers. Integer tokens are range-checked lexically before numeric conversion;
only values 0 through 9007199254740991 are admitted. The token `-0` retains its
existing canonicalization to `0`; signed payloads must still be canonical. Root objects are closed. Identifiers match `[a-z0-9][a-z0-9._-]{0,63}`;
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
All supplied key metadata is validated even for unselected keys. This checks the
closed metadata schema and key digest binding; it is not proof of key generation,
ownership, mathematical validation of every unselected key, or trust enrollment.
The authenticated policy provider owns enrollment of valid publisher keys.

`verify(envelope, policy, *, now_s, minimum_time_s, minimum_policy_revision, expected_subject_sha256)`
requires caller-trusted UTC time, a persisted policy revision floor and the exact
expected software artifact digest. The caller must persist the greatest accepted
policy revision and trusted time across calls/restarts, independently of whether an
individual passport succeeds. A newer revocation policy can reject every affected
passport and return no passport-result metadata. These stateless functions cannot
detect caller rollback. Pass the persisted time floor as `minimum_time_s`; time below it fails.
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

## Independent pinned-policy validation

`validate_pinned_policy(policy, *, expected_policy_sha256, now_s, minimum_time_s,
minimum_policy_revision)` validates the complete existing v1 policy independently of
any passport. The expected digest must come from authenticated configuration; computing
it from an untrusted download does not establish trust. Validation checks immutable
byte/depth/lexical bounds, every policy field and key metadata, exact SHA-256 equality,
the revision floor, and the half-open policy interval against caller-trusted time.
Policy JSON need not be canonical: whitespace changes require a different exact pin.
The existing `verify` API and signature profile are unchanged.

The frozen result has status `validated` and reason `policy_matches` on success,
with `policy_sha256`, `policy_revision` and `expires_at`. On rejection these three
metadata fields are null. Rejection reasons are `invalid_input`, `time_rollback`,
`policy_mismatch`, `policy_rollback`, and `policy_not_current`. All results have
`execution_authority`, `motion_authority` and `evidence_verified` false. Results are
ordinary constructible application values, not unforgeable authorization tokens.

A policy revoking all its signers can validate successfully. Validation neither proves
key ownership nor requires an available crypto backend; it checks policy metadata and
the externally provisioned content pin. This does not authenticate a policy transport,
persist a floor, detect same-revision equivocation across calls, or enroll trust.
Later consumers must use these exact policy bytes and recheck current time/floors.
See the [decision and C4 boundary](../../engineering/reviews/p16-policy-admission-v3.md).

The optional [local policy-floor store](policy-floor-store-v1.md) supplies explicit
single-scope persistence for cooperating processes on protected local storage. It
does not change these stateless APIs or establish trust in the clock, pin or storage.

## Validation and limits

Use a published test-only signing seed; fixture keys are never deployment trust roots.
Retain tampered, expired, revoked, future, unknown-key, scope, authority and malformed
negative cases. Test actual Ed25519 signatures and a golden DSSE PAE vector, resource
limits before decoding, and seeded bounded parser mutation. Missing crypto must reject.
Default dependency-free installs retain the parser and fail closed on signature checks;
install the `passports` extra for Ed25519. The workflow configures separate checks of
this extra; configuration alone is not evidence that a hosted run passed. See the
[verification evidence boundary](verification-evidence-v1.md).
No hardware, certification, live evidence, production, or complete revocation claim.

## Deployment claim boundary

This offline Ed25519/DSSE profile does not implement an MLS system, a cross-domain
guard, encrypted transport, or CNSA qualification. Neither a valid signature nor a
capability name establishes those properties. It has no hard real-time deadline,
five-nines availability evidence, target-hardware latency qualification, or tactical
interoperability accreditation. Insufficient information for tactical deployment.
A future qualified cryptographic profile needs a distinct version and independently
verified deployment evidence; this profile must not silently change algorithms.
