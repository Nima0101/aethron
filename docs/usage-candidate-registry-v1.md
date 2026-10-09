# Offline candidate registry entry v1

`aethron.evaluation.registry.validate` checks one immutable, caller-pinned entry
joining a candidate, its card and rights declaration, two split manifests and
opaque evaluation-evidence bytes. It reruns the existing declaration gates.
It preserves expired, revoked, pending and denied rights states in the result.
A valid entry is not an approved model or permission to use one.

## Technology decision

Requirements are deterministic offline checks on bounded documents, explicit
provenance bindings, denial preservation and no model execution, network access
or new runtime dependency. There is no real-time or database requirement for
this entry-validation component. Python's standard-library hashing/JSON with
the strict parser and independent semantic validators satisfies those bounds;
it can compose the gates without an additional serialization/process boundary.

The [OCI descriptor specification](https://specs.opencontainers.org/image-spec/descriptor/?v=v1.1.1)
documents digest and byte-size checks before content consumption. This contract
adopts those checks but is not an OCI manifest or distribution implementation.
[SQLite atomic transactions](https://www.sqlite.org/atomiccommit.html) provide
useful guarantees for a future mutable catalog, but no storage transaction is
needed to validate an immutable entry. A registry server or transactional
database would add deployment/state requirements without strengthening this
contract. Signature verification and peer-owned passport logic remain separate.

## Entry format

The root is a UTF-8 JSON object with exactly four fields:

| Field | Requirement |
| --- | --- |
| `version` | Integer `1`, not Boolean |
| `kind` | `offline_candidate` |
| `protocol_sha256` | Lowercase 64-character SHA-256 digest |
| `documents` | Exactly the six roles below |

Each document descriptor contains exactly `sha256` (lowercase SHA-256) and
`bytes` (positive integer, not Boolean). The caller supplies the actual bytes
separately. No descriptor contains a path, URL, mutable tag or remote locator.

| Document role | Maximum bytes | Validation |
| --- | ---: | --- |
| `candidate` | 16,384 | Candidate v1 bound to training manifest and protocol |
| `card` | 16,384 | Card v1, including its candidate/rights references |
| `rights` | 16,384 | Rights v1 with operation fixed to `offline_evaluation` |
| `training_manifest` | 2,097,152 | Split manifest v1 |
| `evaluation_manifest` | 2,097,152 | Split manifest v1 plus declared holdout separation |
| `evaluation_evidence` | 2,097,152 | Byte identity only; opaque, never parsed or executed |

The entry itself is at most 16,384 bytes. Entry and structured documents reject
duplicate JSON keys, nonfinite values and nesting beyond eight levels. Unknown
fields and roles reject. Every input must be immutable `bytes`. Document sizes
and digests are checked before downstream semantic validation. No referenced
model, preprocessing or dataset artifact is opened by this API.

## Library API and trust boundary

```python
from aethron.evaluation.registry import validate

report = validate(
    entry_bytes,
    candidate=candidate_bytes,
    card=card_bytes,
    rights=rights_bytes,
    training_manifest=training_manifest_bytes,
    evaluation_manifest=evaluation_manifest_bytes,
    evaluation_evidence=evaluation_evidence_bytes,
    expected_entry_sha256=trusted_entry_digest,
    expected_review_sha256=trusted_review_digest,
    now_s=trusted_now,
    minimum_time_s=trusted_clock_floor,
    revoked_rights_sha256s=trusted_revocations,
)
```

Obtain pins, time, the rollback floor and revocations from caller-controlled
trusted configuration. Deriving a pin from an untrusted entry does not establish
trust. The entry pin binds all document digests and the protocol declaration.
The independent review pin, clock and revocation inputs retain the constraints
of [rights assessment v1](usage-candidate-rights-v1.md); the evidence named by
the review digest is not loaded or authenticated here.

Invalid structure, mismatched bytes or references, invalid caller inputs or
declared split leakage raise fixed `ValueError("invalid_registry_entry")` with
no partial report. Inactive rights declarations remain valid records of negative
evidence: `rights_declaration_active` is false with `rights_reason` from the
rights gate. Consumers must not treat `registry_entry_valid` as permission.

The report includes the entry/protocol bindings, all six document descriptors,
review pin, evaluated time, time floor and revocation-set digest. It emits no
card source metadata, dataset rows or evidence payload. Structural card and
declared separation checks are true on success. `evaluation_bytes_verified`
means only that the supplied opaque bytes match the descriptor.
`evaluation_semantics_verified`, `model_artifacts_verified`, `rights_verified`,
`review_verified`, `dataset_rights_verified`, `qualified` and `runtime_admitted`
are always false.

In particular, evidence bytes can claim `qualified: true` without affecting
these flags. The validator does not establish that the evidence describes this
candidate, that an evaluation ran, that any metric passed or that an evaluator
signed a result. It neither stores entries nor implements a registry index,
update ordering, promotion, deployment, CLI or runtime activation. Those require
separate versioned contracts. Synthetic fixtures demonstrate software checks
only; they provide no physical or legal qualification.

Run the focused tests with
`PYTHONPATH=tests python3 -m unittest test_candidate_registry`.
