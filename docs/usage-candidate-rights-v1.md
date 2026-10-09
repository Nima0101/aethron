# Candidate rights-review declarations v1

`aethron.evaluation.rights.assess` evaluates the declared status, scope, validity
window and supplied revocations of a candidate's rights-review record. It is
an offline library API, with no model execution, network access or filesystem
reads. This new optional record format leaves existing opaque rights blobs,
frozen model cards and evaluation protocols unchanged.

A positive `declared_permission` describes the supplied record only. It is not
authorization to train, evaluate or distribute anything. `rights_verified`,
`review_verified`, `dataset_rights_verified` and `qualified` always remain false.
The review evidence itself is neither loaded nor authenticated. Independent
rights review and dataset permissions remain separate prerequisites.

## Inputs and trust boundary

Call `assess(rights_bytes, candidate_bytes, manifest_bytes, ...)` with all these
required keyword arguments:

- `expected_candidate_sha256`, `expected_manifest_sha256`,
  `expected_protocol_sha256`: trusted pins for the existing candidate validator.
- `expected_review_sha256`: separately trusted pin identifying the review
  evidence. Copying it from the rights record provides no independent trust.
- `operation`: `offline_evaluation`, `offline_training` or
  `artifact_redistribution`. These tokens do not cover live inference or actuation.
- `now_s`, `minimum_time_s`: trusted integer timestamps in the same seconds epoch,
  each from 0 through 2^53−1; `now_s` must be at least the caller's time floor.
- `revoked_rights_sha256s`: an explicit tuple of at most 1024 lowercase SHA-256
  digests. An empty tuple declares that the caller supplied no revocations.

The caller owns the pins, trusted time source, persisted time floor and current
revocation snapshot. The function does not discover missing revocations, refresh
trust or maintain monotonic state. The floor rejects a supplied rewind only
when the caller carries forward the correct floor. Reassess using fresh trusted
inputs at each use; a prior report is not an admission token.

The candidate and manifest must pass their existing strict validators. The
candidate's pinned `rights_sha256` must match the exact rights bytes, including
whitespace. No separate rights pin is needed because the candidate pin binds it.

## Record v1

Rights records are UTF-8 closed JSON, at most 16,384 bytes and depth 8. All fields
below are required; unknown or duplicate keys, nonfinite values and boolean
timestamps/versions reject.

| Field | Constraint |
|---|---|
| `version` | Integer `1` |
| `artifact_sha256`, `preprocessing_sha256`, `protocol_sha256`, `training_manifest_sha256` | Equal the respective validated candidate digests |
| `review_sha256` | Equal the separately supplied review pin |
| `status` | `approved`, `denied`, `pending` or `revoked` |
| `uses` | Unique list of supported operation tokens; approved records require at least one; other statuses may use an empty list |
| `valid_from_s`, `expires_at_s` | Integers from 0 through 2^53−1, with start strictly before expiry |

The validity interval is half-open: start is included, expiry is excluded. This
record refers to artifact/preprocessing/manifest/protocol bindings; it does not
refer back to a candidate/card hash and create a digest cycle. The review pin
is a reference to external evidence, not a new signature mechanism. Human names,
free-form license interpretations and private review text are outside this
record schema.

Malformed records, incorrect pins or invalid caller inputs raise the fixed
`ValueError("invalid_candidate_rights")`, without returning partial output.
Such errors must not be converted into permission by a consumer.

For valid inputs, reasons are evaluated in this order:

1. A supplied revocation matches the rights digest: `record_revoked`.
2. Status is not approved: `review_denied`, `review_pending` or `review_revoked`.
3. Time precedes the start: `not_yet_valid`.
4. Time reaches or exceeds expiry: `expired`.
5. The operation is absent from `uses`: `out_of_scope`.
6. Otherwise: `declared_scope_active`.

Only the last reason sets `declared_permission: true`. These fixed reasons
preserve negative outcomes without exporting private reviewer metadata.

## Report bindings

Reports contain version `1`, check `candidate_rights_declarations_v1`, candidate
and rights digests, the four subject-binding digests, review digest, requested
operation, `evaluated_at_s`, `minimum_time_s`, `revocations_sha256`, reason,
declared permission, and the four false verification/qualification flags above.

The revocation digest is SHA-256 of the ASCII bytes
`aethron.rights-revocations.v1`, one zero byte, then the concatenated ASCII
digests in the sorted distinct revocation set. Each digest is exactly 64 bytes,
so boundaries are fixed. Reordering or repeating entries preserves this hash;
the 1024-entry input bound applies before deduplication. Empty input hashes the
domain prefix and zero byte. This hash records the supplied set, not proof that
it is complete, current or authoritative. Digests are linkable, not anonymized.

## Technology decision — 2026-10-10

Requirements are deterministic offline assessment, bounded JSON, exact subject
bindings, integer time checks, explicit denial and no ambient authority or
background service. There is no sensor SDK or real-time inference dependency.

Reviewed [OPA policy-language defaults](https://www.openpolicyagent.org/docs/policy-language),
[W3C ODRL's permission/prohibition model](https://www.w3.org/TR/odrl-model/) and
[SPDX licensing metadata](https://spdx.dev/learn/areas-of-interest/licensing/).
OPA/Rego offers a general policy engine; its runtime and policy-evaluation
surface exceed this fixed three-operation decision table. ODRL offers broader
rights/obligation modeling that this minimal record does not implement. SPDX
identifiers describe licensing metadata, not this record's review or revocation
decision. No compatibility or compliance with those standards is claimed.

Selected explicit Python standard-library checks over the bounded byte reader:
all operations are hashing, fixed field validation, bounded membership and
integer comparisons. No plugin loading, policy expressions, new dependencies,
downloaded weights or hardware claims are introduced. A different implementation
can be compared against the versioned fixtures if deployment requirements change.

Original synthetic tests cover approval/denial states, scope mismatch, both time
boundaries, caller clock rewind, revocations, report bindings, malformed records,
input limits and wrong subject/review pins. They prove software behavior only.
