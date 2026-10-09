# Authenticated rollout plan binding v1

## Requirements and technology decision (2026-10-10)

Bind signed policy fields and exact software artifact bytes to journal pins, with
bounded local I/O, restart rollback floors, untrusted source paths and no execution
side effects. The source directory may change while it is being inspected.

Select a Python adapter with standard-library private temporary directories,
64KiB streaming copies and the existing OpenSSL verifier. A native Go/Rust
snapshot service could enforce equivalent file bounds but would add executable
packaging, IPC and another trust-boundary serialization for this small local
operation. Direct verification of a mutable directory leaves a second-read
binding problem. A bounded private snapshot avoids that problem without inventing
a new signature format or replacing the verifier. Files are removed after checking;
this component is not a retained artifact cache or installation service.

Primary sources: [Python temporary file/directory semantics](https://docs.python.org/3/library/tempfile.html)
and [TUF client workflow](https://theupdateframework.github.io/specification/latest/).
The latter informs authentication, rollback and expiry checks; this component
makes no TUF conformance claim. Snapshot guarantees assume the trusted local
process, pinned key and OS temporary-directory isolation remain intact.

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

The two durable files are **not a cross-file atomic transaction**. If final expiry,
exclusive creation or journal persistence fails after the floor commit, floors
stay advanced. An existing journal and its failures are never overwritten. A
failed journal initialization may leave an unusable file requiring explicit local
recovery. Failures use `ValueError("invalid_fleet_plan")`; no lower floor is restored
to make a retry succeed. Private snapshot cleanup precedes durable success state.

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
fabric, real activation and physical qualification remain separate work.

## Focused tests

Real ephemeral Ed25519 signatures exercise exact pins/fields, source replacement
after snapshot copying, artifact/signature tampering, malformed and backward time,
expiry before and after floor commit, floor commit rejection, existing-journal
preservation, and missing/link/extra/oversized input members. A sparse oversized
file tests the size rejection; no large artifact processing or hardware job runs.
