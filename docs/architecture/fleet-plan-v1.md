# Authenticated rollout plan binding v1

The [fresh V3 review](fleet-plan-review-v3.md) confirms bounded streaming and
corrects the technology and cleanup claims. The [V2 audit](fleet-plan-technology-audit-v2.md)
retains evidence of the post-journal-commit timing correction. The API, signed
format and size/time limits remain unchanged.

## Requirements and technology decision

Bind signed policy fields and exact software artifact bytes to journal pins, with
bounded local I/O, restart rollback floors, mutable source paths and no execution
side effects. The synchronous Python adapter combines bounded native file reads,
incremental SHA-256 and private temporary storage. Rust/native and C# adapters can
implement the same interface without a service or IPC; Erlang/Elixir is also a
credible candidate. The V3 assessment finds no demonstrated material migration
winner under this local contract. Tool availability and rewrite cost are not
selection criteria. No comparative speed or hardware qualification is claimed.

Private copied bytes are checked and hashed; verifying the mutable source and
then reopening it would leave a binding problem. Snapshot guarantees assume the
trusted process, pinned key and OS directory isolation remain intact. Cleanup is
attempted before persistence. This is neither a retained artifact cache nor an
installation service, and temporary-file deletion is not secure erasure.

## Input and API

`create_rollout_plan(bundle, public_key, *, journal_path, floor_store, clock)`
requires an existing protected floor database and caller-owned trusted UTC.
The source directory contains exactly these four regular files:

| Name | Maximum size |
| --- | ---: |
| `manifest.json` | 8192 bytes |
| `manifest.sig` | 64 bytes, exact signature size checked by verifier |
| `fleet-policy.json` | 2048 bytes |
| `fleet-artifact.bin` | 8MiB |

The manifest uses the existing signed bundle v1 format and must authenticate
exactly the two payload members. The fixed file names are never caller-selected
archive paths. At most five directory entries are examined, so an extra entry
rejects the bundle without an unbounded inventory walk. Symbolic links, special
files, truncation and growth beyond the inspected size are rejected by bounded
regular-file copying. A coherently signed snapshot can be admitted even if the
original directory later changes; no directory immutability claim is made.

## Ordering and partial failure

1. Read persistent floors and sample trusted time at or above their time floor.
2. Copy the four bounded files into a new private directory, hashing the copied
   bytes. Verify signature, manifest membership, hashes and policy fields there.
3. Resample time, rejecting rollback or expiry. Remove the temporary snapshot.
4. Commit authenticated version/time floors. A competing newer floor or failed
   commit prevents journal creation.
5. Resample time again, then exclusively create the bounded journal with the
   copied policy/artifact hashes and authenticated policy version, capacity,
   batch size and validity window.
6. After journal initialization returns, resample time and require a strict integer
   no earlier than the creation sample and before exclusive expiry. Return the
   journal only after this check. This fourth sample is checked, not persisted.

The two durable files are **not a cross-file atomic transaction**. If final expiry,
exclusive creation or journal persistence fails after the floor commit, floors
stay advanced. An existing journal and its failures are never overwritten. A
failed journal initialization may leave an unusable file requiring explicit local
recovery. Failures use `ValueError("invalid_fleet_plan")`; no lower floor is restored
to make a retry succeed. Expected cleanup failure prevents both durable updates. Successful context exit
precedes persistence, but a crash or actual removal failure may leave temporary
files. The trusted host must protect any residue; this API neither guarantees
secure deletion nor performs a broad temporary-directory sweep.

## What the result means

The journal is inert bookkeeping bound to bytes verified in the private snapshot.
The artifact is never executed, unpacked or installed. No private temporary path
or raw payload is stored in the journal, and no device/person identity is added.
The artifact is not retained: a later executor must reacquire and verify its
exact bytes before use. `allow_initial_provisioning` is not an authorization
issued by this API; any future provisioning operation must reverify that policy
permission at its own boundary.

Concurrent admission may supersede a floor immediately after this call commits.
I/O stalls may outlast a sampled validity window. Plan creation and reservation
therefore confer no lasting operation authority. Execution needs its own current
trust/time/floor checks, content binding and capability admission. Database-backup
rollback protection, key rotation, recovery of unfinished reservations, network
fabric and physical qualification remain outside this API. No MLS/CNSA,
hard-real-time or five-nines assurance is established. Insufficient information
for tactical deployment.

## Focused tests

Real ephemeral Ed25519 signatures exercise exact pins/fields, source replacement
after snapshot copying, artifact/signature tampering, malformed and backward time,
expiry before and after floor commit, floor commit rejection, existing-journal
preservation, and missing/link/extra/oversized input members. A sparse oversized
file tests the size rejection; no large artifact processing or hardware job runs.

Sixteen focused plan tests pass in the V3 review. The added test injects an error
at snapshot context exit after actual temporary cleanup, verifying the fixed
public error, no journal and unchanged floors. This validates failure ordering,
not successful removal under every filesystem fault or process crash. See the
[source-bound evidence](../verification/fleet-plan-review-v3.json).
