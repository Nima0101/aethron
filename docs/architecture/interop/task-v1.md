# Offline task description v1

This profile describes two local verification requests: `passport.verify.v1` and
`evidence.bind.v1`. Validation does not execute, schedule, authorize or reserve anything.
The closed shape has no controller, location, person-identity, command, URL or filesystem
path fields. An identifier or digest is not anonymous merely because its syntax is restricted;
producers must not encode personal identifiers in task IDs or digest references.
Every result denies execution authority, motion authority and evidence qualification.

## Technology decision

Constraints: bounded immutable input, portable exact bytes, offline operation on desktop
OSs, no service or real-time scheduling dependency, caller-provisioned digest pins and
trusted time/floors, no new crypto protocol. The input is an untrusted description until
its canonical bytes match the externally authenticated task digest. A digest taken from
the same untrusted description is not an authentication mechanism.

Compare [CloudEvents](https://cloudevents.io/) event routing, deterministic
[CBOR](https://www.rfc-editor.org/rfc/rfc8949.html), and closed canonical JSON. CloudEvents
provides a transport-neutral event envelope but not this admission policy; CBOR saves
wire space but would introduce another deterministic encoding profile. Choose closed
ASCII JSON for these small software-only descriptions, with explicit frozen v1 bounds.

For execution compare Rust/Serde typed decoding, .NET/System.Text.Json token decoding,
Node/TypeScript, and Python with lexical hooks. Rust and .NET are credible bounded
parser choices; neither removes digest-pin, cross-field or expiry checks. Node's default
JSON parser loses duplicate properties and number spellings, as the
[policy-v2 probe](../../engineering/plans/p16-technology-audit-v2.md) demonstrates.
[Python hooks](https://docs.python.org/3/library/json.html) preserve those distinctions
with a small validation surface and exact immutable bytes. Choose Python here, sharing
the audited internal v1 byte parser and canonical encoder with passports. This shares
syntax code only; no self-declared passport grants task authority. A new streaming,
embedded or throughput requirement must reopen the decision. No new dependencies.
The [fresh component review](../../engineering/reviews/p16-task-v3.md) compares the
current bounded implementation with native token readers and the Elixir ecosystem.

## Contract

Exact UTF-8 bytes, at most 65536 bytes, depth 8, duplicate/unknown fields and float lexemes
rejected. Canonical ASCII JSON has sorted keys and compact separators. Required fields:

| Field | Rule |
| --- | --- |
| `version` | exact integer 1 |
| `task_id` | 1–64 lowercase ASCII identifier characters, same token grammar as passport v1 |
| `kind` | `passport.verify.v1` or `evidence.bind.v1` |
| `subject_sha256`, `passport_sha256`, `policy_sha256` | lowercase SHA-256 digests of the software artifact, exact envelope bytes and exact policy bytes |
| `evidence_sha256` | ordered list of unique digests; empty for passport verification, 1–16 for evidence binding |
| `issued_at`, `expires_at` | safe integer UTC seconds; positive lifetime at most 300 seconds |
| `max_evidence_bytes` | exact integer 0 for passport verification; 1–1048576 for evidence binding |
| `motion_authority` | literal false |

`validate_task(raw, *, expected_task_sha256, expected_subject_sha256, now_s,
minimum_time_s)` rejects noncanonical bytes, malformed pins, pin/subject mismatch,
clock rollback and time outside `[issued_at, expires_at)`. All time inputs are exact safe
integers. It returns fixed rejection reasons without echoing untrusted data. Success
returns immutable metadata and `execution_authority=false`. Rejections omit the task
digest and expiry metadata. Results are snapshots of a check at caller-supplied time;
saved positive results do not expire themselves and cannot serve as fresh authorization.
`canonicalize_task` checks shape only: it has no trusted clock or authenticated digest pin.

Digest pins bind a description, not the truth of its referenced artifacts. This function
does not load the referenced bytes or validate their signatures. The existing
[bundle verifier](task-bundle-v1.md) binds supplied local bytes and checks current passport
trust against the caller's supplied policy snapshot. Consumers must supply trusted
time and policy floors and apply their own authorization and replay policy. Repeating
the same valid request succeeds again; there is no replay storage or exactly-once claim.
The passport/evidence verifiers reject expired policy and revoked keys or statements
listed in that policy. They do not discover a newer policy or independently revoke an
evidence digest. Failed or unknown signed evidence outcomes remain metadata; binding
bytes never converts them into a passed result or physical qualification.
