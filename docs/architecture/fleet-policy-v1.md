# Fleet policy v1 — signed local admission

This P3.4 library admits fleet rollout configuration from an administrator-local,
signed bundle. It does not install software, reboot devices, provision network
credentials, contact hosts or operate vehicle interfaces. P11 collection and
transport authorization remain separate work.

## Requirements and technology decision (2026-10-10)

Requirements are bounded configuration bytes, a pinned offline trust root,
verified content provenance, expiry using trusted time, a caller-supplied durable
rollback floor, no device identity/location data and no hardware assumptions.
The configuration must remain portable across qualified host runtimes; parsing
has no real-time requirement. No new network service or privileged installer is
needed for local admission.

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

Select a strict Python data parser composed with the existing OpenSSL Ed25519
bundle verifier. This keeps signature verification in a maintained crypto
implementation and avoids a new process boundary, persistent service or native
binding for a 2048-byte configuration. Go's standard-library Ed25519 and Rust
verifier libraries are credible for a future independent daemon, but would need
an executable distribution and IPC contract here. A TUF client adds repository
roles and metadata not supplied by this offline bundle format; RAUC adds slot
and platform integration outside this admission component. Existing code has no
exemption: its verifier is reused only for its signed-byte and regular-file
contracts. This is not a TUF/Uptane/RAUC compliance or compromise-resilience claim.

## Frozen additive v1 contract

`load_fleet_policy(bundle, public_key, *, now_unix_s, minimum_version)` returns an
immutable `FleetPolicy` only after `verify_bundle` succeeds. `fleet-policy.json`
must be a signed member of the bundle. Read at most 2049 bytes through the bounded
regular-file reader and verify the exact parsed bytes against the signed SHA-256
digest again, so replacement after bundle verification cannot change the policy.
The caller must supply a locally pinned public key and an administrator-controlled
bundle directory. Full bundle verification retains the existing v1 limits and
may read all signed payloads; this is not an untrusted network request handler.

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

## Focused implementation plan

1. Write real signed-bundle tests before implementation: time/version boundaries,
   schema/privacy rejection, tamper, wrong key and post-verification replacement.
2. Implement the immutable policy and loader in `runtime/fleet_policy.py`.
3. Run only focused tests/lint/security; keep prior fleet-health staging intact
   until its pending commit-bridge request is fulfilled. No frozen core changes.
