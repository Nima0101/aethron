# Offline dataset split checks

Run `python -m aethron.evaluation.splits manifest.json` before preparing a new training/evaluation corpus. Exit 0 means the descriptors satisfy the structural checks; exit 2 means rejection. Output contains split counts, the exact input SHA-256 and protocol digest. Descriptor-only validation reports `qualified`, `artifacts_verified` and `rights_verified` as false. It does not read referenced artifacts. Neither mode downloads, trains, grants data-use rights or verifies signatures.

Version 1 is closed JSON with these fields:

| Object | Required fields |
|---|---|
| Root | `version: 1`, `protocol_sha256`, `provenance`, `samples` |
| Provenance | `id`, `source`, `origin`, `license`, `evidence`, `rights_sha256`, `card_sha256`, `allowed_splits` |
| Sample | `id`, `split`, `session_sha256`, `artifact_sha256`, `source_sha256`, `provenance_id` |

IDs are 1–64 ASCII letters, digits, underscores or hyphens. Digests are lowercase 64-character SHA-256 strings. Source, origin and license are nonempty text of at most 512 characters, with no surrounding whitespace or control characters. Evidence is `synthetic` or `recorded`. Splits are `train`, `validation`, `test`; each must contain at least one sample. Every sample references one provenance record and a split declared in that record's `allowed_splits`. Unused or duplicate provenance IDs are rejected.

The protocol digest must identify the evaluation protocol frozen before selecting or evaluating model candidates. The rights digest identifies the independently reviewed rights record, and the card digest identifies the card covering intended/forbidden uses, format, transformations and limitations under the [provenance policy](engineering/model-data-provenance.md). Declaring these hashes does not prove the records exist or are approved; verify their bytes and authority separately before use.

The session digest identifies an acquisition session or flight, never a person. Its assignment must remain consistent across related datasets and transformations. A renamed session cannot be detected from descriptors alone. Source digests identify original sample bytes; artifact digests identify the bytes used by the consumer. Both content digests share one comparison namespace. No content digest or session may span splits; duplicate artifact entries are rejected even within one split. Multiple transformations of the same source/session may occur within one split when artifact hashes differ. Similar but nonidentical samples with incorrectly declared lineage remain outside these structural checks.

Input is limited to 2 MiB, nesting depth 8, 128 provenance records and 4096 samples. The split CLI requires a regular manifest file: final-component symlinks, FIFOs and directories reject with `invalid_split_manifest`. It shares the bounded document reader with the proposal CLI; exactly 2 MiB is permitted. Parent directories must be trusted, and no filesystem I/O deadline is implied. Duplicate JSON keys, nonfinite values, unknown fields and malformed metadata are rejected without echoing source content. See [synthetic test fixtures](../tests/test_dataset_splits.py) for a complete manifest example and failure cases.

This prepares new split manifests only. Existing frozen AOT and synthetic evaluation inputs remain unchanged; their historical results are not reclassified as held-out model qualification.

Candidate artifacts can separately bind this manifest and its training split through the [offline model-candidate validator](usage-model-candidates.md). This does not grant training or runtime approval.

## Optional local blob verification

Use `python -m aethron.evaluation.splits manifest.json --blob-dir blobs` or `verify_artifacts(manifest_bytes, blob_dir)` to check referenced bytes. Store each blob directly under that directory, named by its lowercase SHA-256. The verifier checks every protocol, card, rights-record, source and artifact reference; session digests are grouping identifiers, not blob references. Shared hashes are read once, while `verified_references` counts each role's references. Success reports `artifacts_verified: true`, `verified_blobs` and `verified_bytes`. `rights_verified` and `qualified` remain false: matching rights-record bytes proves neither permission nor authenticity.

This POSIX implementation pins a directory descriptor, opens entries without following symlinks, rejects nonregular files, and reads at most 64 KiB per chunk. Limits are 64 MiB per unique blob and 256 MiB total. It checks sizes, digests, file metadata and path identity after each read. Missing, modified, oversized or unsafe blobs reject the entire result. The CLI retains exit 2 and a fixed error without paths or payloads; the API raises `invalid_split_artifacts` for blob failures and `invalid_split_manifest` for descriptor failures.

The selected root must not be a symlink, including spellings with trailing `/` or `/.`; its parent path is trusted operator configuration. Platforms lacking the required descriptor-relative/non-following operations fail closed. Checks describe bytes observed during this call, not an immutable snapshot of the directory: consumers must reverify or retain verified bytes before subsequent use. No approval, signature trust, dataset lineage correctness or model qualification follows from this report.

## Consuming verified sample bytes

Call `load_split(manifest_bytes, blob_dir, "test", expected_manifest_sha256=manifest_digest, expected_protocol_sha256=protocol_digest)` to consume one split. Supply both digests from caller-controlled evaluation configuration. The manifest digest binds its exact bytes, including whitespace. Invalid pins or split names raise `invalid_split_selection` before filesystem access; existing descriptor/blob errors remain distinct.

Each call verifies every referenced blob afresh, including references belonging to other splits. The result is a frozen `LoadedSplit` containing manifest/protocol digests, the selected split and a tuple of frozen `LoadedSample` records in manifest order. Each sample contains its sample ID, artifact/source/session digests, provenance ID, declared evidence kind and immutable `data` bytes. Raw bytes are omitted from the generated representation. `rights_verified` and `qualified` remain false.

Consume `sample.data` directly. It is retained from the same descriptor reads that passed the artifact hash check, so later disk replacement cannot alter the returned sample. No paths or file descriptors escape, and no partial result is returned if another reference fails. Up to 256 MiB of selected payloads can be retained under the existing aggregate limit, with up to one additional 64 MiB transient join allocation plus bounded metadata. Release the result when finished. This is an offline corpus-loading bound, not a real-time edge memory claim. An earlier `verify_artifacts` report is never accepted as a substitute for fresh checks; the filesystem itself is still not an atomic snapshot or an approved dataset.

## Running the offline pixel baseline

Run `python -m aethron.evaluation.proposals manifest.json --blob-dir blobs --split test --manifest-sha256 MANIFEST_DIGEST --protocol-sha256 PROTOCOL_DIGEST`, or call `aethron.evaluation.proposals.run` with the same inputs as `load_split`. All referenced blobs must verify, and every selected artifact must be a supported P5 grayscale image. The runner uses the existing, unchanged `detect_pgm` obstacle-proposal baseline on retained sample bytes. CLI manifest and annotation inputs must be regular files of at most 2 MiB; final-component symlinks, FIFOs, directories and oversized files reject with `invalid_proposal_input` and no report. Parent directories must be trusted; these checks do not impose a filesystem I/O deadline.

Before detection it validates every selected image and enforces separate offline work budgets: at most 300 frames and 16,777,216 total pixels, with the existing decoder's 640×512 per-image bound. These limits do not replace or relax frozen runtime thresholds. No complete report is returned when validation fails. The CLI exits 2 with a fixed error and no partial stdout; exit 0 means execution completed, not that a qualification gate passed.

The deterministic JSON report binds manifest/protocol digests and the requested split, then gives frame count, frames with proposals, proposal count and declared synthetic/recorded evidence counts. It exports no sample IDs, paths, raw pixels or boxes. `training` is `none`; `accuracy_evaluated`, `rights_verified` and `qualified` are false. No ground truth is consumed, so these counts are neither precision/recall nor evidence of person/UAV classification. Frozen AOT results remain unchanged.

## Optional obstacle annotation metrics (protocol v1)

Supply both `--annotations labels.json --annotations-sha256 LABEL_DIGEST` to the proposal CLI, or `annotations=label_bytes, expected_annotations_sha256=label_digest` to `run`. Omitting both preserves counts-only behavior; supplying only one rejects. The exact annotation bytes, manifest and protocol must all match caller-controlled pins. The runner verifies all blobs afresh and validates all labels/images before detection. Labels never enter the detector.

Annotation version 1 is closed JSON: root fields are `version: 1`, `manifest_sha256`, `protocol_sha256`, `split`, `samples`. Each sample row has exactly `sample_id`, `artifact_sha256`, `boxes`. Every selected sample must appear exactly once with its exact artifact digest; row order is immaterial. Each box is normalized `[x, y, width, height]`, finite numeric values in [0,1], positive extent and wholly inside the image. Boolean coordinates, duplicate boxes, more than 64 boxes per sample, missing/extra rows and unknown fields reject. Empty boxes explicitly label a negative frame. The shared strict JSON limits remain 2 MiB and depth 8. No semantic class or temporal identity fields are accepted.

This mode requires the exact protocol bytes exported as `aethron.evaluation.annotations.PROTOCOL_BYTES`, whose SHA-256 is `PROTOCOL_SHA256`. Store those bytes as the manifest's protocol blob **before** evaluating candidates. UTF-8 protocol contents below include one trailing newline:

```json
{"version":1,"task":"obstacle_proposals","iou_min":0.3,"matching":"max_cardinality_then_iou","box":"normalized_xywh","max_boxes_per_frame":64}
```

For each frame, eligible pairs have IoU >= 0.3. One-to-one assignment maximizes match count, then total IoU, using deterministic ties. Aggregate TP is matched pairs, FP is unmatched proposals and FN is unmatched labels. Precision and recall are rounded to six decimal places; a zero denominator yields null. This separate protocol uses existing geometry/assignment helpers without changing frozen temporal metrics or AOT results. Future matching changes require a new protocol version.

The report adds `annotations_sha256`, `metrics_scope: supplied_obstacle_annotations`, and `metrics` containing `true_positives`, `false_positives`, `false_negatives`, `precision`, `recall`; `accuracy_evaluated` becomes true only in this mode. It still reports `qualified: false`, `rights_verified: false`, `training: none`, and declared evidence counts. These are comparisons against supplied labels, not proof of annotation quality, protocol pre-registration, held-out independence, rights, field accuracy, semantic person/UAV capability or tracking performance. Synthetic fixtures verify software behavior only. The API reports invalid labels/pins/protocol as `invalid_annotations`; CLI errors retain fixed stderr, exit 2 and empty stdout.

Annotated reports also include `metrics_by_evidence`, with separate `synthetic` and `recorded` groups. Each group has `frames` plus the same TP/FP/FN/precision/recall fields; absent groups have zero counts and null ratios. Aggregate metrics remain available, but mixed synthetic/recorded results must not be presented as recorded accuracy. Group membership comes only from the manifest's declared evidence kind and does not verify how images were acquired.

## Optional per-provenance report v2

Add `--per-provenance` (API: `per_provenance=True`) with pinned annotations to expose sources whose misses are hidden by pooled metrics. This selects report `version: 2` and adds `metrics_by_provenance`: a digest-keyed object containing `frames`, TP/FP/FN, precision and recall for each provenance represented in the selected split. Empty denominators remain null. At most 128 groups are possible under the existing manifest bound. A source absent from the selected split is omitted. Counts sum to the pooled counts; matching and detector semantics are unchanged. `--baseline all` uses comparison `pgm_obstacle_baselines_v2` with two v2 reports. Omitting the option preserves the existing v1 output exactly. The API requires a boolean option; enabling it without valid pinned annotations rejects.

Each group key is SHA-256 of the ASCII bytes `aethron.provenance.v1` followed by one zero byte and the complete declared provenance record serialized with Python JSON `sort_keys=True, separators=(",", ":"), ensure_ascii=True`, without a trailing newline. Keys are stable across object-key, sample and provenance-record reordering; record content changes (including its ID or array order) change the digest. The report sorts digest keys and exports no raw provenance metadata, sample IDs or paths. These deterministic hashes are linkable and are not encryption or anonymization of guessable metadata. They identify declarations, not verified real-world sources or independent acquisition. Rights and qualification remain false.

## Comparing pixel baselines

Select `--baseline classical_pgm_obstacle_v1` (the unchanged default), `--baseline global_pgm_obstacle_v1`, or `--baseline all`. The API accepts the same `baseline` keyword. Unknown selections reject before manifest/blob access. Single-baseline output keeps the existing report shape; `all` returns `{version: 1, comparison: pgm_obstacle_baselines_v1, reports: [...], rights_verified: false, qualified: false}`, with the local-contrast report first and fixed-threshold report second. Each report carries its own baseline ID and identical manifest/protocol/annotation bindings. Counts-only comparisons remain supported when annotations are omitted.

Comparison verifies and loads samples once, validates all selected images and annotations, then runs both detectors against the same retained bytes. A later on-disk replacement cannot give the second baseline different input. No partial comparison is printed. The 300-frame/16,777,216-pixel input budgets remain; comparison executes two bounded detector passes and is not a real-time resource claim.

### Fixed-threshold comparator card v1

`global_pgm_obstacle_v1` is an original deterministic rule baseline, with no learned weights or training. It uses the existing bounded P5 decoder, selects pixels <=127, groups eight-connected pixels, keeps components of 3–1200 pixels, sorts by descending pixel count then normalized box coordinates, and emits at most 32 obstacle proposals. Its constant score 0.6 and variance 0.0001 are interface placeholders, not calibrated probabilities or uncertainty. Range is null. These settings were declared before its synthetic regression results; changes require a separately named version. Source and tests are [baselines.py](../aethron/evaluation/baselines.py) and [test_dataset_baselines.py](../tests/test_dataset_baselines.py), under GPL-3.0-only.

Candidate selection retains 32 components after each insertion (33 transiently), in the same size/box order. Pixel decoding, the foreground mask and traversal stack still depend on image size; this is not a bound on whole-process memory.

The comparator tests software behavior against the local-contrast baseline. A uniform dark image can become a false proposal; bright objects, small components and components above the size limit can be missed. Neither grayscale intensity nor a connected component establishes object identity, semantic class, physical distance or thermal meaning. Use only for offline obstacle-proposal comparisons on separately rights-reviewed data; no person/UAV, live safety, actuation or field qualification follows. Frozen runtime detectors, temporal metrics and AOT data/results are unchanged.

## Reproducing original synthetic fixtures

Run `python -m aethron.evaluation.synthetic NEW_DIRECTORY`, or call `aethron.evaluation.synthetic.generate(new_directory)`. The parent must exist and be trusted operator configuration. The destination must not exist: files, symlinks and even empty directories reject without replacement. This POSIX implementation uses directory descriptors, exclusive non-following file creation and atomic, non-replacing publication of the completed `pins.json`. Unsupported filesystem operations fail closed. A failed run preserves its output for inspection; it never recursively deletes or resumes an existing directory. Interrupted pins writes cannot publish the completion file. This is not a power-loss durability guarantee; consumers still verify all hashes.

The output contains `manifest.json`, `annotations-train.json`, `annotations-validation.json`, `annotations-test.json`, `pins.json`, and twelve SHA-256-named files under `blobs/` (nine PGM images, the matching protocol, an original-generation rights statement and a fixture card). No timestamp, absolute path or random seed enters the content. The CLI prints the same pin object on success; failure exits 2 with `invalid_fixture_output` and no partial stdout. Pins identify exact manifest/protocol/annotation bytes, with `evidence: synthetic`, `training: none`, `rights_verified: false` and `qualified: false`.

Each split contains three 8×8 frames: an annotated dark patch, an annotated bright patch, and an unannotated uniform dark frame. Split variants have distinct image/source hashes and synthetic session identifiers, but closely related generation rules: they are **not statistically independent held-out accuracy data**. No model is trained and no external image is downloaded. Do not treat the miss and false-positive fixtures as errors to tune away.

Use the generated files with the existing CLI:

```text
python -m aethron.evaluation.proposals NEW_DIRECTORY/manifest.json --blob-dir NEW_DIRECTORY/blobs --split test --baseline all --annotations NEW_DIRECTORY/annotations-test.json --manifest-sha256 MANIFEST_DIGEST --protocol-sha256 PROTOCOL_DIGEST --annotations-sha256 TEST_ANNOTATION_DIGEST
```

Copy the three digests from `pins.json` (`annotations_sha256.test` for the test split). For each split the local-contrast baseline gives TP=1, FP=0, FN=1, and the fixed-threshold baseline gives TP=1, FP=1, FN=1. These hand-designed outcomes reproduce software behavior and known limitations, not thermal/person/UAV, field or safety accuracy. Frozen datasets and baseline settings remain unchanged. All generated fixture content is original and GPL-3.0-only; the evaluator's rights flags intentionally remain unapproved.

## Probing comparison CLI timing

After installing the core wheel into a dedicated environment, run the checkout's `scripts/dataset_cli_timing.py NEW_DIRECTORY --repetitions 3` with that environment's Python, preferably from outside the checkout. The script uses the interpreter's selected AETHRON package for both its reference and child CLI processes; it does not insert checkout sources into the import path. Input must be the exact `synthetic_pgm_v1` fixture, including complete pins. The script is an offline development tool, not part of the runtime wheel.

The harness verifies an untimed reference comparison, then runs 1–5 fresh `python -m aethron.evaluation.proposals` processes. Each observation includes process startup, imports, blob checks, both baselines, report output and reaping. It is **not** isolated inference time, a cold filesystem-cache measurement, a real-time deadline guarantee or physical latency qualification. Reference work can warm filesystem caches. Raw elapsed samples are kept separate from deterministic metrics; no percentile or accuracy claim is inferred from these tiny inputs.

Each child has a 10-second observation deadline and a 64 KiB combined stdout/stderr capture cap. A timeout or output overflow kills and reaps that child; failures are recorded without retry. OS process creation and cleanup may themselves add delay beyond the observation deadline. Exit zero is accepted only with empty stderr and a strict, complete comparison equal to the verified reference. Duplicate keys, changed bindings, boolean/integer substitutions, missing fields and other differences reject. Child payloads, command paths and raw stderr are not returned.

JSON output includes fixture digests, canonical reference digest, hashes of the harness and selected package's Python sources, Python/platform identifiers, `source_stable`, and raw samples (`elapsed_ms`, `status`, `returncode`, captured stdout/stderr byte counts). Source hashes are observations before/after the run, not signed execution attestation. A source change or failed final source read preserves the samples but makes `all_succeeded` false. `qualified` is always false. CLI exit 0 means all observations succeeded with stable source hashes; exit 1 retains the report with a failed observation or source binding; exit 2 reports `invalid_timing_input` for setup/input rejection. Historical timeout and release-gate failures remain separate evidence even if this probe succeeds.

## Fuzzing the dataset APIs

With AETHRON installed, run `python path/to/scripts/dataset_fuzz.py --cases 3000 --seconds 60 --seed 472` from outside the checkout. The script does not alter the import path. It generates and verifies an original synthetic fixture in its own temporary directory, then exercises descriptor validation, annotation validation/matching and the global PGM baseline. It does not fuzz the full filesystem loader, local-contrast detector or temporal runtime.

Each three-case round visits all three APIs; every fifth round uses known valid controls. Other rounds mutate bytes, truncate, append invalid bytes or substitute malformed inputs. Annotation digests are recomputed for mutations so validation reaches structural checks. Reports include accepted/rejected/control counts, input and case-stream digests, observed source hashes and a sanitized first failure index/digest. They omit payloads, paths and exception text. The same seed and completed case count reproduce the input stream; time-limited runs can complete different prefixes.

Limits are 1–10,000 cases and more than zero through 60 seconds of case execution. The clock is checked between calls and after the last call; it cannot interrupt a stuck call. Setup, source hashing and cleanup are outside that interval. Use an external process deadline when one is needed. Source hashes are observations, not signed execution attestations. Exit 0 requires every requested case to finish within budget with stable sources and no unexpected result; exit 1 retains partial/failure evidence, and exit 2 indicates invalid arguments or setup. These development checks do not replace full fuzz qualification, rights review or hardware evidence.

Add `--reports` to select a separate v2 fuzz campaign for the real proposal-report API. Its three targets mutate annotation content with a recomputed annotation pin, the annotation pin itself, and an owned source blob. Every case runs fresh blob verification and both detectors with per-provenance reports enabled. The owned synthetic fixture stays alive through this campaign, and mutated source bytes are restored between cases. Three declared sources cover supported/negative test frames, a missed test frame and unselected train/validation frames; they are synthetic test declarations, not independent recorded datasets.

Every fifth report-mode round replaces the annotation malformed-seed case with a valid structural mutation, cycling through empty labels, displaced labels and extra unmatched labels. Annotation pins are recomputed; these variants test reporting behavior, not detector tuning. Other targets retain malformed-seed cases.

The report oracle uses hand-established boxes for the three fixture images and the unchanged matching protocol against each accepted annotation mutation. It checks the complete report, group membership and counts, including exclusion of the unselected source, pooled totals, null ratios, pins and false qualification flags. Unexpected fields and boolean/numeric substitutions fail. The same case/time budgets, source binding, sanitized failures and cleanup apply; time limits remain cooperative, including for filesystem calls. The report mode emits fuzz report version 2. Without `--reports`, the original three-target mutation stream and v1 report remain unchanged. Neither campaign replaces full qualification.

## Locating split CLI stalls

Run the installed-environment timing script with `--documents --repetitions 3` and no dataset-directory argument. Each repetition creates three fresh child processes that invoke the real split CLI entry point on owned FIFO, symlink and malformed regular-file fixtures. All three must reject with code 2. The wrapper reports that code separately from its own exit status and records `startup`, `import_start`, `import_end`, `read_start`, `read_end` and `done` markers. This instrumented entry-point execution differs from the original `python -m` invocation and is diagnostic evidence, not a timing-equivalence claim.

The existing 10-second and combined 64-KiB limits apply per child, with no retries. A child schedules a stack dump after five seconds; the parent retains at most 16 stack-line SHA-256 digests, fixed stage labels and numeric times. It discards raw stderr, paths and traceback text. Unexpected stderr, incomplete/out-of-order markers or a stack dump cannot count as successful completion. A timeout retains any captured marker prefix and stack digests.

The first marker follows interpreter startup and the bootstrap's `sys`/`time` imports. No marker therefore cannot distinguish scheduler, interpreter or bootstrap stalls. Stage nanoseconds are relative to the child's bootstrap clock, while outer elapsed time also includes startup and cleanup. Instrumentation perturbs timing. Passing later probes do not explain or clear historical failures, and unchanged source hashes are observations rather than execution attestations.

Filesystem CLI operations and dataset fuzz/timing harnesses require POSIX
descriptor primitives (`O_NOFOLLOW`, `O_NONBLOCK`, `O_DIRECTORY`, directory-relative
open/stat; fixture creation also requires directory-relative mkdir/link/unlink
and non-following links). Missing capabilities reject with the existing fixed
error and no successful report. Fixture generation rejects before creating its
destination; fuzzing rejects before creating scratch space. Windows is currently
unsupported for these filesystem paths. In-memory descriptor validation remains
portable. A capability check does not qualify a filesystem: every subsequent
operation, hash and resource bound is still checked.
