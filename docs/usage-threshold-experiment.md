# Experimental PGM threshold fitting v1

`experimental_pgm_threshold_v1` is a CPU-only obstacle proposal experiment,
separate from the unchanged fixed global and local baselines. It is not a
thermal, UAV, semantic, calibrated-confidence or physical capability claim.

The following search is declared before fitting: thresholds 31, 63, 95, 127,
159, 191 and 223; maximize pooled training F1, compared as exact rational
numbers, with zero for a zero denominator. Break ties by fewer false positives,
then the smaller threshold. Use the existing inclusive IoU 0.3 maximum-cardinality
then IoU matcher. No held-out labels select parameters.

Preprocessing is the existing bounded P5 grayscale decoder (at most 640×512),
with no resize, normalization, crop or augmentation. Pixels at or below the
threshold form eight-connected components of area 3–1200. Retain the first 32
ordered by descending area then normalized xywh; score 0.6 is not calibrated.
The parameter schema contains one integer `threshold` from the declared grid.
Fit/evaluate accept at most 64 selected frames and 1,048,576 total selected pixels;
fit makes seven detector passes. These bound work, not elapsed time. Dataset
verification retains its existing 64 MiB/blob and 256 MiB total read bounds.

`aethron.evaluation.threshold.fit` accepts manifest bytes, a blob directory and
**only train annotation bytes**, with required manifest/protocol/annotation pins.
It returns canonical JSON model bytes, bound to the training manifest, train
annotations, preprocessing and search digests. `evaluate` takes these model bytes
and their independently supplied SHA-256, the same pinned manifest, a validation
or test split and separately pinned annotations. It never fits or changes the
model. Model JSON is closed, bounded to 4 KiB, and contains no executable format.
It does not interpret opaque candidate descriptors as models.

All dataset blobs are hash-verified for split integrity, but fitting decodes and
scores only train samples. Changing held-out annotation files cannot affect fit.
The API cannot establish that a caller has not relabeled data or repeatedly
tuned experiments after inspecting test results. Preserve externally preregistered
splits and pins. Hashes are integrity bindings, not signatures, rights approval,
label-quality approval or proof that an imported model was actually fitted.

CLI (pins must come from independently retained inputs):

```sh
python -m aethron.evaluation.threshold fit manifest.json --blob-dir blobs \
  --manifest-sha256 MANIFEST --protocol-sha256 PROTOCOL \
  --annotations annotations-train.json --annotations-sha256 TRAIN_LABELS > model.json
python -m aethron.evaluation.threshold evaluate manifest.json --blob-dir blobs \
  --manifest-sha256 MANIFEST --protocol-sha256 PROTOCOL \
  --annotations annotations-test.json --annotations-sha256 TEST_LABELS \
  --split test --candidate model.json --candidate-sha256 MODEL
```

Evaluation reports aggregate and per-evidence TP/FP/FN, precision and recall,
with exact input digests and all qualification/rights/signature/training-attestation
flags false. No sample IDs, paths or label geometry are emitted. The original
synthetic PGM fixtures exercise software only; related variants do not establish
independent held-out accuracy. Existing frozen evaluation and runtime limits remain
unchanged.

For a comparison on the same held-out pixels, replace `evaluate` with `compare`
in the command above; the required pins and split arguments are identical.
`threshold.compare` loads and verifies once, then runs the fitted scalar, the
unchanged local-contrast baseline and the unchanged fixed-127 global baseline,
in that order. The 64-frame/1,048,576-pixel preflight bound applies to the whole
selected snapshot, with three detector passes and no fitting.

The comparison envelope is `pgm_threshold_comparison_v1`. Each contained metrics
report uses schema v2 and includes `metrics_by_provenance`: sorted SHA-256 keys
of complete canonical provenance declarations, using the existing
`aethron.provenance.v1` domain separator. Only sources represented in the selected
split appear. These linkable hashes are not anonymization or verified provenance.
Per-source failures remain visible even when pooled metrics look better.
The experiment report retains the candidate, training, preprocessing and search
bindings, and says `training: pinned_train_threshold`; the two fixed reports
retain `training: none`. The candidate model remains schema v1. Comparison never
refits or mutates it, and existing `fit`, `evaluate` and fixed-baseline report
formats remain unchanged.

Export a portable bundle with explicit model-card and rights document pins:

```sh
python -m aethron.evaluation.threshold_bundle model.json \
  --model-sha256 MODEL --manifest manifest.json --manifest-sha256 MANIFEST \
  --protocol-sha256 PROTOCOL --blob-dir blobs --output-dir new-bundle \
  --card model-card.json --card-sha256 CARD \
  --rights rights.txt --rights-sha256 RIGHTS
```

The destination must be new, below a trusted parent. It contains `candidate.json`
(the existing opaque candidate v1 descriptor), the exact `manifest.json`, and
SHA-256-named `blobs/` containing all dataset references, model bytes,
preprocessing/search specifications and supplied card/rights bytes. Thus the
generic candidate verifier can check it offline without the original directory.
No fitting or model execution occurs. Training annotations are not copied or
attested; their digest remains in the model. Card/rights bytes are pinned opaque
declarations, not approval of their content or permission to redistribute data.

Metadata documents are nonempty and at most 2 MiB each; dataset blobs retain
their 64 MiB bound. Copying holds one verified dataset blob at a time. The 256 MiB
budget counts unique dataset reads plus distinct candidate/specification bytes,
including candidate roles also referenced by the dataset. Destination verification
then rereads those bounded files. `pins.json` is published without overwrite only
after metadata readback, candidate verification and the extra search-specification
check succeed. This completion marker is not a signature or power-loss durability
guarantee. Failed exports retain incomplete output for inspection and never reuse
or recursively delete an existing destination. All qualification and attestation
flags remain false.

Verified dataset loading and export currently require POSIX directory-descriptor
and no-follow filesystem operations, as does the existing artifact verifier.
Their integration tests inherit that platform requirement; this is not Windows
filesystem qualification. No weaker filesystem fallback is used.

To verify a moved bundle without the source dataset directory:

```sh
python -m aethron.evaluation.threshold_bundle_verify moved-bundle \
  --candidate-sha256 CANDIDATE --manifest-sha256 MANIFEST \
  --protocol-sha256 PROTOCOL
```

Supply those pins from independently trusted configuration, not from the bundle
being checked. The reader verifies exact canonical completion bytes, all dataset
and candidate references, the scalar model's frozen bindings and the search
specification. It does not fit or execute the model. Candidate/completion metadata
are limited to 16 KiB each; the manifest to 2 MiB. Additional model/search reads
count toward the existing 256 MiB read budget. Use a quiescent directory below a
trusted parent; symlinks and nonregular metadata/blob files are rejected. Success
reports `bundle_verified` and `artifacts_verified`, while rights, signatures,
training, preprocessing qualification and overall qualification remain false.
Failure emits only `invalid_threshold_bundle` on stderr with exit code 2 and no
partial report. Neither export nor verification authenticates pins or approves
redistribution or execution.

To compare that bundle against both existing fixed baselines on held-out labels:

```sh
python -m aethron.evaluation.threshold_bundle_compare moved-bundle \
  --candidate-sha256 CANDIDATE --manifest-sha256 MANIFEST \
  --protocol-sha256 PROTOCOL --split test \
  --annotations test-annotations.json --annotations-sha256 ANNOTATIONS
```

Only `validation` and `test` are accepted. Annotations need an independent trusted
pin and must match the selected manifest/split exactly. The command verifies the
complete bundle, then rechecks model/dataset hashes and compares all three fixed
detectors on one immutable held-out snapshot. It never refits. The JSON envelope
contains `bundle_verification` and the existing `comparison` report, including
per-provenance metrics; qualification stays false. Each verification/evaluation
pass keeps its 256 MiB read ceiling, plus a bounded 16 KiB model reread between
passes. Existing frame/image limits remain unchanged. Integrity verification does
not authenticate pin provenance or establish physical accuracy or model approval.
