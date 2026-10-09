# Offline candidate-card declarations v1

The optional `aethron.evaluation.cards` gate checks a small structured card
against an already pinned [candidate declaration](usage-model-candidates.md).
It supplements opaque byte verification. Existing cards and frozen model
protocols are unchanged; this new schema is explicitly selected by calling this
gate. Passing it means required declarations are present and bound, not that
their contents are true, adequate, licensed, independently reviewed or approved.

```sh
python -m aethron.evaluation.cards card.json \
  --candidate candidate.json --training-manifest manifest.json \
  --candidate-sha256 CANDIDATE_DIGEST \
  --manifest-sha256 MANIFEST_DIGEST --protocol-sha256 PROTOCOL_DIGEST
```

The candidate's `card_sha256` binds the exact card bytes, including whitespace.
The trusted candidate pin therefore binds the card without another independent
pin. Obtain all caller pins from trusted configuration. The candidate and split
manifest must pass their existing validators, including training-split and
declared leakage checks. The card is UTF-8 closed JSON, limited to 16,384 bytes
and depth 8; unknown or duplicate keys, nonfinite values and boolean versions
reject. All fields below are required.

| Field | Constraint |
|---|---|
| `version` | Integer `1` |
| `task`, `format` | Match the candidate: `obstacle_proposals`, `opaque` |
| `format_version` | 1–64 ASCII letters, digits, underscores or hyphens; identifies the declared artifact format revision |
| `artifact_sha256`, `preprocessing_sha256`, `protocol_sha256`, `training_manifest_sha256`, `rights_sha256` | Equal the respective validated candidate digests |
| `source`, `origin`, `license`, `reproducibility` | Each 1–512 printable characters, without surrounding whitespace |
| `intended_use` | `offline_obstacle_evaluation` |
| `limitations` | 1–16 distinct text entries, each with the same text constraints |
| `forbidden_uses` | Each of the seven tokens below exactly once, in any order |

Required forbidden-use tokens are `biometric_identity`,
`cross_scene_reidentification`, `person_history`, `targeting`, `weapons`,
`autonomous_pursuit`, and `live_safety`. These are declarations within this
offline candidate-card format, not executable controls or changes to v3's
permitted ephemeral safety tracking. A future runtime integration still needs
its own admission, privacy and qualification gates.

Text fields are inert metadata: URLs are not fetched, reproducibility prose is
not executed, and artifacts are never deserialized. Control characters,
nonprintable characters and lone surrogates reject. A nonempty license string
does not establish permission. This is a minimal structural record, not a
complete scientific model report or an interpretation of legal terms.

The API is `validate(card_bytes, candidate_bytes, manifest_bytes,
expected_candidate_sha256=..., expected_manifest_sha256=...,
expected_protocol_sha256=...)` from `aethron.evaluation.cards`.
Success returns version `1`, check `candidate_card_declarations_v1`, candidate
and card digests, the five reference digests, and `card_structure_valid: true`.
`artifacts_verified`, `rights_verified`, `training_verified` and `qualified`
remain false. The report contains no source, origin, license prose,
reproducibility instructions or limitations text. Digests are linkable bindings,
not anonymization or signature verification. No evaluation score is inferred.

The API raises `ValueError("invalid_candidate_card")` on rejection. CLI input
failures exit 2 with fixed stderr and empty stdout; successful execution exits 0
with sorted JSON. Argument-syntax diagnostics use argparse. The shared regular
document reader rejects final symlinks, FIFOs and directories and reads at most
2 MiB per document before the tighter card/candidate acceptance limits apply.
Trusted parent directories and lack of a filesystem I/O deadline remain the
same as in the candidate CLI. No partial report is emitted.

## Technology decision — 2026-10-10

Requirements: offline operation, exact byte pins, strict bounded input, no
model execution or resident service, deterministic output, a small shared Linux
host, and compatibility with portable evaluation consumers. There is no sensor
latency requirement or SDK dependency for this metadata check.

The [Model Cards paper](https://arxiv.org/abs/1810.03993) motivates recording
intended use and limitations. [JSON Schema object rules](https://json-schema.org/understanding-json-schema/reference/object)
provide a declarative alternative for required/closed fields, but raw-byte
duplicate rejection and cross-document digest bindings still need separate
code. [Go's JSON documentation](https://pkg.go.dev/encoding/json) describes
compatibility behavior, including duplicate-key handling in its v1 API; a
standalone implementation would need an explicitly strict parser contract and
an additional binary distribution path. These are implementation choices, not
language exclusions or performance measurements.

Selected Python standard-library validation with an explicit closed schema and
the bounded byte reader. The 16 KiB card cap and small fixed field set make a
separate schema engine, network schema resolver or compiled service unnecessary
for this increment. No new runtime dependency, downloaded model or hardware
claim is introduced. If future throughput/deployment evidence changes these
constraints, compare alternatives using this public byte/error contract.

Original synthetic fixtures cover all reference mismatches, missing metadata,
forbidden-use omissions/duplicates, private-output suppression, exact byte
bounds and CLI tampering. They establish software behavior only. Independent
rights review, factual provenance, usable reproduction procedures and model
qualification remain external evidence requirements.
