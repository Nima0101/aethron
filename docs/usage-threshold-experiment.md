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
