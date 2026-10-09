# Offline model-candidate declarations

`python -m aethron.evaluation.candidates` checks a new candidate declaration against a pinned [dataset split manifest](usage-dataset-splits.md). It does not load a model, run preprocessing, train, download or approve an artifact. Existing rule/vision models and their frozen cards are unchanged. This implements structural preparation under the [model/data provenance policy](engineering/model-data-provenance.md).

## Candidate descriptor v1

The input is closed JSON, at most 16,384 bytes and depth 8. Duplicate keys, unknown fields, nonfinite values, invalid types and malformed digests reject. All fields below are required:

| Field | Required value |
|---|---|
| `version` | Integer `1`, not boolean |
| `task` | `obstacle_proposals` |
| `format` | `opaque` |
| `artifact_sha256` | Candidate artifact digest |
| `preprocessing_sha256` | Preprocessing specification digest |
| `protocol_sha256` | Dataset manifest's evaluation protocol digest |
| `training_manifest_sha256` | Digest of the exact supplied split-manifest bytes |
| `training_split` | `train`; `validation` and `test` reject |
| `card_sha256` | Candidate card digest |
| `rights_sha256` | Candidate rights-record digest |

Every digest is a lowercase 64-character SHA-256 string. `opaque` means only that referenced bytes can be hashed. It is not a runtime format, executable loading permission, or a claim of ONNX/pickle compatibility. Card, rights and preprocessing records remain uninterpreted: their completeness, authority and semantic correctness require separate review. The protocol digest is bound, not interpreted as an approved evaluation protocol. The candidate must not be treated as an accepted inference provider.

## API and CLI

Call `aethron.evaluation.candidates.validate(candidate_bytes, manifest_bytes, expected_candidate_sha256=..., expected_manifest_sha256=..., expected_protocol_sha256=...)`. Obtain pins from caller-controlled configuration; copying them from untrusted input does not establish trust. The candidate pin binds all its artifact/record references. The dataset manifest must pass existing split validation, including declared cross-split content/session separation, and its digest/protocol must match both the candidate and caller pins.

```sh
python -m aethron.evaluation.candidates candidate.json \
  --training-manifest manifest.json \
  --candidate-sha256 CANDIDATE_DIGEST \
  --manifest-sha256 MANIFEST_DIGEST \
  --protocol-sha256 PROTOCOL_DIGEST
```

Without `--blob-dir`, this checks declarations only and never opens referenced artifacts. The report contains the descriptor's fixed tokens and digests, the candidate digest and the declared training-sample count. It emits no sample IDs, source metadata, paths or model bytes. `artifacts_verified`, `training_verified`, `preprocessing_verified`, `rights_verified`, `signatures_verified` and `qualified` are false.

Use `--blob-dir blobs`, or `verify_artifacts(candidate_bytes, manifest_bytes, blob_dir, ...same pins...)`, to additionally hash the referenced bytes. The directory holds SHA-256-named regular files. Every dataset reference, including validation/test artifacts, is verified first; the distinct candidate artifact/preprocessing/card/rights references are then checked afresh with the same non-following, chunked reader. Success sets only `artifacts_verified` true and adds `verified_bytes` and `verified_blob_reads`. Other flags remain false. No partial report is returned on failure.

Each blob is limited to 64 MiB; total bytes read across the dataset and candidate checks are limited to 256 MiB. Candidate references repeated within the candidate are read once. A candidate reference also used by the dataset is read and counted again. No candidate payload is retained or parsed. This POSIX implementation rejects nonregular files and final-component/root symlinks, including trailing-slash/dot root aliases. Parent directories are trusted operator configuration. These successive checks are observations of pinned bytes, not an atomic filesystem snapshot or an I/O deadline guarantee.

CLI documents use the shared bounded regular-file reader (at most 2 MiB read per document); the candidate's tighter 16 KiB acceptance limit still applies. CLI success exits 0 with sorted JSON. Rejection exits 2, with empty stdout and fixed stderr `invalid_model_candidate`. API validation and blob errors use that same fixed `ValueError` message.

A valid declaration does not prove training occurred, that training used only the declared split, that a source is independently held out, or that any rights/signature/accuracy requirement passed. Byte identity cannot establish these claims. Synthetic opaque fixtures exercise the checker only. Runtime integration, rights review, signed provenance and full candidate/physical qualification remain separate gates.

For a separate evaluation corpus, the [candidate test-separation gate v1](usage-candidate-holdout-v1.md) binds both manifests and rejects declared test content or acquisition sessions shared with the candidate's training/validation data. This remains a declaration check, with no rights or qualification promotion.

The optional [structured candidate-card gate v1](usage-candidate-cards-v1.md) requires bounded source, origin, license, intended/forbidden-use, reproducibility and limitation declarations, and matches their artifact/protocol/rights bindings to the candidate. It validates structure only; rights and qualification remain unverified.

The optional [rights-review declaration assessment v1](usage-candidate-rights-v1.md) checks pinned review metadata, operation scope, trusted time inputs and supplied revocations. Its positive result describes an active declaration only; it never grants legal rights, dataset permission or model qualification.

The [immutable registry-entry validator v1](usage-candidate-registry-v1.md) joins these declarations with both manifests and opaque evaluation-evidence bytes. It reruns the gates, preserves inactive rights states and verifies byte bindings without treating evidence content as a passed evaluation or runtime admission.

The [offline registry update-proposal gate v1](usage-registry-updates-v1.md) checks a pinned predecessor, consecutive revision, caller rollback floor and expiry window, then reruns registry validation. It reports declaration checks only and never commits catalog state or authorizes deployment.

## Bounded candidate fuzzing

Run `python scripts/dataset_fuzz.py --candidates --cases 300 --seconds 5` with AETHRON available. This separate v3 fuzz report exercises rebound descriptor mutations, wrong candidate pins and tampered opaque artifacts through the real verifier. Every fifth artifact round uses a sparse 64 MiB + 1 byte file to exercise the blob-size rejection without writing that much data. The case-stream marker identifies this sparse-size operation; it is not the oversized file's content digest. Owned fixtures and mutations are restored/removed after the run. Reports contain counts, digests and fixed failure reasons, never payloads or paths. The existing cooperative time/case budgets and source binding apply; setup/cleanup are outside the timed interval. `--candidates` and `--reports` are mutually exclusive; earlier default/report streams are unchanged. This is development coverage, not full fuzz qualification.
