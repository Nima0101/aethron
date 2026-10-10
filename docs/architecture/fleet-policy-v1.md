# Fleet policy v1 — signed local admission

This P3.4 library admits fleet rollout configuration from an administrator-local,
signed bundle. It does not install software, reboot devices, provision network
credentials, contact hosts or operate vehicle interfaces. P11 collection and
transport authorization remain separate work.

## Requirements and technology decision (2026-10-10)

Requirements are bounded configuration bytes, a pinned offline trust root,
verified content provenance, expiry using trusted time, a caller-supplied durable
rollback floor, no device identity/location data and no hardware assumptions.
The JSON boundary is portable; qualification of a particular host runtime is
not established by this format. Parsing has no specified real-time deadline.
No network service or privileged installer is needed for local admission.

Reviewed primary sources:
- [TUF specification](https://theupdateframework.github.io/specification/):
  signature verification, expiry and rollback checks protect different properties.
- [Uptane design](https://uptane.org/learn-more/design): separate artifact trust
  from selection/deployment authority; secure time is an explicit input.
- [RAUC reference](https://rauc.readthedocs.io/en/latest/reference.html):
  compatibility and slot configuration belong to a device-specific installer.
- [Go Ed25519](https://pkg.go.dev/crypto/ed25519),
  [Rust ed25519-dalek](https://docs.rs/ed25519-dalek/latest/ed25519_dalek/) and
  [OpenSSL pkeyutl](https://docs.openssl.org/3.5/man1/openssl-pkeyutl/):
  credible verification implementations with different runtime/packaging costs.

The [fresh V3 review](fleet-policy-review-v3.md) retains strict Python admission
composed with the shared native OpenSSL verifier. Verification already launches
an OpenSSL subprocess; there is no process-free implementation claim. Native
alternatives can use bindings and do not inherently require IPC or a daemon.
The decision rests on strict bounded parsing, immutable results and one shared
verification boundary, not existing tooling or rewrite cost. A TUF client adds
roles and metadata absent from this offline format; RAUC adds platform/slot
integration outside this component. This is not a TUF/Uptane/RAUC compliance or
compromise-resilience claim.

## Frozen additive v1 contract

`load_fleet_policy(bundle, public_key, *, now_unix_s, minimum_version)` returns an
immutable `FleetPolicy` only after `verify_bundle` succeeds. `fleet-policy.json`
must be a signed member of the bundle. Read at most 2049 bytes through the bounded
regular-file reader and verify the exact parsed bytes against the signed SHA-256
digest again, so replacement after bundle verification cannot change the policy.
The caller must supply a locally pinned public key and an administrator-controlled
bundle directory. Full bundle verification retains the existing v1 limits and
may read all signed payloads; this is not an untrusted network request handler.

The key file must be a regular non-symlink file of at most 1024 bytes containing
one `PUBLIC KEY` PEM block. Its canonical Base64 decodes to the exact 44-byte
RFC 8410 Ed25519 SubjectPublicKeyInfo shape: prefix
`302a300506032b6570032100` and 32 public-key bytes, with no ASN.1 parameters or
trailing DER. LF/CRLF body wrapping is accepted. The loader privately snapshots
these admitted key bytes before the verifier reads them. This is an algorithm
and encoding allowlist, not certificate validation or trust-root distribution.

The shared v1 verifier currently permits a 2 MiB manifest, 8192 signed members
and 512 MiB per payload. Its inventory walk and payload hashing have no overall
wall-clock deadline; the five-second OpenSSL timeout bounds only that subprocess
operation. The 2048-byte policy limit therefore does not bound all bundle work.
The caller must protect the directory, key selection, executable search path
and temporary-file environment. This loader is not a defense against a malicious
administrator or a same-user process that can modify its private scratch files.

Policy JSON is strict UTF-8, at most 2048 bytes, with exactly these fields:

| Field | Constraint |
|---|---|
| schema_version | integer 1 |
| bundle_version | integer 1..2^31-1; equals signed manifest version |
| not_before_unix_s | integer 0..2^53-1 |
| expires_unix_s | integer 0..2^53-1; lifetime 1..86400 seconds |
| slot_count | integer 1..1024 |
| batch_size | integer 1..32 and <= slot_count |
| allow_initial_provisioning | strict boolean |

Reject unknown/duplicate keys, nonfinite and boolean numbers, nested values,
invalid UTF-8 and any expired/not-yet-valid policy. Admission requires
`not_before_unix_s <= now_unix_s < expires_unix_s` and
`bundle_version >= minimum_version`. Clock and floor inputs obey the same strict
integer domains; the minimum version is at least 1. All rejection paths use
`ValueError("invalid_fleet_policy")` without echoing file contents or paths.

The result is configuration, not a transferable authorization token. A rollout
executor must reverify at use, retain a durable version/time high-water mark,
bind authorized devices to slots, and fail closed on missing health. This parser
does not persist floors, establish UTC trust, prevent replay across a caller
reset, certify artifact compatibility or approve activation. An initially empty
installation may use floor 1; existing installations must supply their durable
floor. Policy lifetime never renews on load. `batch_size` and provisioning flags
are constraints for the future executor, not implemented rollout behavior.

## Verification and qualification limits

Seventeen focused tests exercise real synthetic Ed25519 signatures, wrong roots,
tampering, time/version bounds, strict encodings and replacement races. They also
reject an RSA signature of the same length under an RSA root and malformed key
profiles. These establish tested software behavior, not cryptographic-module
certification, deployment readiness or the truth of signed declarations.

`load_fleet_policy` evaluates the supplied time once; it cannot notice elapsed
time during verification. Consumers needing a post-verification check must use
the separately reviewed admission boundary and revalidate at use. No returned
object is lasting permission to deploy.

This format implements neither encryption at rest/in transit, MLS isolation,
CNSA/Suite B compliance, threshold signing nor key rotation/revocation metadata.
It provides no hard real-time or uptime guarantee. Insufficient information for
tactical deployment. Separate versioned protocols and exact qualification
evidence would be required for any broader claim.
