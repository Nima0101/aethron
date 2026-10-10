# Candidate test-separation declarations v1

Use `python -m aethron.evaluation.holdout` before evaluating an opaque candidate
against a separately declared test corpus. This supplements the existing
[candidate declaration](usage-model-candidates.md) and
[split validation](usage-dataset-splits.md). It does not execute a model or read
referenced blobs. Existing frozen protocols, thresholds and results are unchanged.

```sh
python -m aethron.evaluation.holdout candidate.json \
  --training-manifest development.json \
  --evaluation-manifest evaluation.json \
  --candidate-sha256 CANDIDATE_DIGEST \
  --manifest-sha256 DEVELOPMENT_MANIFEST_DIGEST \
  --evaluation-manifest-sha256 EVALUATION_MANIFEST_DIGEST \
  --protocol-sha256 PROTOCOL_DIGEST
```

Obtain all four SHA-256 pins from caller-controlled configuration. The candidate
must bind the exact development manifest, declare training on `train`, and pass
the existing closed candidate schema. Both manifests must independently pass
the existing closed split schema and bind the same pinned protocol. Each still
requires nonempty train, validation and test splits; this is not a test-only
manifest format. The protocol is identified, not interpreted or approved.

Every evaluation `test` sample is checked against every development `train` and
`validation` sample. Source and artifact digests share one comparison namespace:
a raw/derived alias in either direction rejects. Equal acquisition-session
digests also reject, even if image bytes differ. Validation is included because
model or threshold selection can use it. Session digests group acquisitions,
never people. Renaming sample/provenance IDs cannot bypass these checks.

The same manifest may serve both roles. Overlap with development `test` samples
is allowed because this gate excludes declared development data, not earlier
test use. It cannot establish test novelty, honest lineage, absence of prior
tuning, correct session grouping, or completeness of training declarations.
Renamed sessions and undeclared transformations remain outside its evidence.
There is no fuzzy matching, appearance embedding or identity linkage.

The API is `aethron.evaluation.holdout.validate(candidate_bytes,
training_manifest_bytes, evaluation_manifest_bytes,
expected_candidate_sha256=..., expected_manifest_sha256=...,
expected_evaluation_manifest_sha256=..., expected_protocol_sha256=...)`.
Input limits remain 16 KiB for the candidate and 2 MiB for each manifest,
depth 8, 4096 samples and 128 provenance records per manifest. Membership checks
use sets bounded by those sample counts. No downloads or dependencies are added.

Successful output is deterministic sorted JSON with version `1`, check
`candidate_test_separation_v1`, all four input bindings, `development_samples`
(train plus validation), `evaluation_samples` (test), and
`declared_test_separation: true`. `artifacts_verified`, `rights_verified`,
`training_verified` and `qualified` remain false. It exports no sample/session
IDs, per-sample hashes, source descriptions or paths. Input bindings are still
linkable digests, not anonymization.

The API raises `ValueError("invalid_candidate_holdout")` on rejection. The CLI
exits 2 with that fixed stderr and no partial stdout for input/validation errors;
success exits 0. CLI argument syntax errors use ordinary argparse diagnostics.
Documents use the existing bounded regular-file reader: final symlinks, FIFOs
and directories reject. Parent paths are trusted operator configuration;
there is no filesystem I/O deadline. No rights or training approval follows
from matching declarations. Verify blobs and obtain independent rights and
provenance review before actual dataset use.

## Technology decision and primary research

Requirements are offline deterministic comparisons, strict JSON bounds, exact
byte pins and no model loading. On 2026-10-09, reviewed the
[scikit-learn GroupKFold documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html)
for acquisition-group separation and
[Python hashlib documentation](https://docs.python.org/3/library/hashlib.html)
for standard SHA-256 support. GroupKFold generates partitions; this gate audits
already frozen declarations, so a numerical/dataframe dependency is unnecessary.
Python standard-library sets and the existing bounded readers satisfy these
requirements. Native code would add a build boundary without a demonstrated
resource need for at most 8192 sample rows. No upstream implementation is copied.

Original synthetic tests cover content aliases, validation/session leakage,
input pins, malformed documents, deterministic CLI output and unsafe files.
They establish software behavior only, with no accuracy or physical claim.
