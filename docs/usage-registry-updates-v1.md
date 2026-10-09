# Offline registry update proposal v1

`aethron.evaluation.updates.validate` checks a pinned proposed successor to an
offline candidate registry entry. It compares the declared predecessor and
revision with caller-controlled current state and a rollback floor, checks an
expiry window, and reruns registry validation on the actual document bytes.
It never writes state, installs a model or grants deployment permission.

## Technology decision

Requirements: Linux-compatible deterministic offline validation, small bounded
JSON, explicit current-state/time inputs, preserved negative evidence, no model
execution, and no additional service. This component has no real-time deadline,
SDK constraint or persistent-write requirement.

[TUF's versioned metadata and expiration checks](https://theupdateframework.github.io/specification/v1.0.36/)
inform the predecessor/revision/time checks. This proposal format is not TUF:
it provides no root keys, signature thresholds, repository roles or authenticated
metadata discovery. Caller pins must already be trusted.

[Rust/Serde byte-slice parsing](https://docs.rs/serde_json/latest/serde_json/fn.from_slice.html)
offers typed deserialization but would require a new build and integration
boundary for the existing independently tested semantic gates. With a 4 KiB
proposal and no measured latency requirement demanding native code, Python's
standard library and the bounded strict parser meet this component's needs
without a new runtime dependency. [SQLite transactions](https://www.sqlite.org/lang_transaction.html)
are appropriate when persistent catalog writes are added; pure validation
cannot claim their atomicity. These choices are specific to this component.

## Frozen proposal fields

The proposal is at most 4,096 UTF-8 JSON bytes, with exactly these fields:

| Field | Requirement |
| --- | --- |
| `version` | Integer `1` |
| `kind` | `offline_registry_update` |
| `previous_entry_sha256` | Exact caller-pinned current entry digest |
| `entry_sha256` | New entry digest, distinct from the predecessor |
| `revision` | Exactly caller `current_revision + 1` |
| `valid_from_s` | Start of the declared window, inclusive |
| `expires_at_s` | End of the declared window, exclusive and greater than start |

Digests are lowercase 64-character SHA-256 strings. Revisions and times are
integers in `0..2**53-1`; Booleans are rejected. The current revision must be at
least the caller's `minimum_revision`. Exhaustion at the largest revision
rejects every successor. Duplicate/unknown fields, nonfinite values and nesting
beyond eight levels reject. Proposal and all document inputs are immutable bytes.
Initial catalog bootstrap and history lookup are outside this contract.

## API

```python
from aethron.evaluation.updates import validate

report = validate(
    proposal_bytes, entry_bytes,
    candidate=candidate_bytes, card=card_bytes, rights=rights_bytes,
    training_manifest=training_manifest_bytes,
    evaluation_manifest=evaluation_manifest_bytes,
    evaluation_evidence=evaluation_evidence_bytes,
    expected_proposal_sha256=trusted_proposal_digest,
    expected_current_entry_sha256=trusted_current_entry_digest,
    current_revision=trusted_current_revision,
    minimum_revision=trusted_revision_floor,
    expected_review_sha256=trusted_review_digest,
    now_s=trusted_now, minimum_time_s=trusted_clock_floor,
    revoked_rights_sha256s=trusted_revocations,
)
```

Supply trusted configuration independently of the proposal. The proposal pin
binds the new entry, predecessor, revision and expiry. The caller must obtain
the current digest/revision as a consistent pair and maintain its rollback
floors independently. Copying these values out of untrusted documents does not
protect against rollback. All [registry-entry v1](usage-candidate-registry-v1.md)
checks run again; a cached or caller-supplied success report is not accepted.

Invalid structure, stale predecessor/revision, failed entry validation or
invalid trusted inputs raise fixed `ValueError("invalid_registry_update")` with
no partial report. A valid but inactive proposal retains `proposal_reason`
(`not_yet_valid` or `expired`); an active one uses `declared_window_active`.
The nested `registry` report independently preserves the rights reason,
revocations digest, clock inputs, document bindings and all unverified flags.
`declaration_checks_passed` is true only when both the proposal window and
rights declaration are active. It conveys no legal or deployment authority.

The report binds the proposal, predecessor, observed current revision, rollback
floor, proposed revision and validity interval. `state_committed`,
`signatures_verified`, `qualified` and `runtime_admitted` are always false.
Evaluation evidence remains opaque, even if it claims a passing result.

This API is a point-in-time check, not an atomic compare-and-swap. Repeated calls
against unchanged caller state can succeed; two competing proposals can each
pass independently. A future persistent catalog must atomically recheck and
advance the expected digest/revision, retain negative evidence, and revalidate
time and revocations at use. No persistence, signing, deployment, fleet update,
live activation or physical qualification is implemented here.

Focused tests: `PYTHONPATH=tests python3 -m unittest test_registry_updates`.
