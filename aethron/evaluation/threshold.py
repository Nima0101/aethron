"""Bounded experimental train-only threshold fit and pinned held-out evaluation."""

import argparse
import hashlib
import json
import sys
from fractions import Fraction

from ..temporal.pixels import decode_pgm, detect_pgm
from .annotations import PROTOCOL_SHA256, count_matches
from .annotations import validate as validate_annotations
from .baselines import detect_global_pgm, detect_threshold_pgm
from .proposals import _metrics, _provenance_digests, _report
from .splits import _hash, _keys, _parse, _read_document, _require, load_split

BASELINE = "experimental_pgm_threshold_v1"
THRESHOLDS = (31, 63, 95, 127, 159, 191, 223)
MAX_FRAMES = 64
MAX_PIXELS = 1048576
MAX_CANDIDATE_BYTES = 4096

# Versioned, predeclared semantics. These bind algorithm specifications, not code
# signatures or runtime approval. Altering them requires a new experiment version.
PREPROCESSING_BYTES = (
    b'{"version":1,"decode":"bounded_p5_640x512","transform":"none",'
    b'"foreground":"pixel_lte_threshold","connectivity":8,"area":[3,1200],'
    b'"max_proposals":32,"order":"descending_area_then_normalized_xywh",'
    b'"class":"obstacle","score":0.6,"variance":0.0001,"range_m":null}\n'
)
SEARCH_BYTES = (
    b'{"version":1,"thresholds":[31,63,95,127,159,191,223],'
    b'"objective":"pooled_train_f1_exact_zero_denominator_is_zero",'
    b'"ties":["fewest_false_positives","lowest_threshold"],'
    b'"split":"train","max_frames":64,"max_pixels":1048576,'
    b'"matching_protocol_sha256":"' + PROTOCOL_SHA256.encode("ascii") + b'"}\n'
)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _encode(doc):
    return (json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _load(data, blob_dir, split, annotations, manifest_pin, protocol_pin, annotation_pin):
    _require(protocol_pin == PROTOCOL_SHA256)
    loaded = load_split(
        data,
        blob_dir,
        split,
        expected_manifest_sha256=manifest_pin,
        expected_protocol_sha256=protocol_pin,
    )
    truth = validate_annotations(annotations, loaded, expected_sha256=annotation_pin)
    _require(len(loaded.samples) <= MAX_FRAMES)
    pixels = 0
    # Validate all selected pixels and work limits before any detector/scoring pass.
    # load_split verifies other split blobs, but does not return their pixels/labels.
    for sample in loaded.samples:
        width, height, _ = decode_pgm(sample.data)
        pixels += width * height
        _require(pixels <= MAX_PIXELS)
    return loaded, truth


def _counts(loaded, truth, threshold):
    totals = [0, 0, 0]
    by_evidence = {"synthetic": [0, 0, 0, 0], "recorded": [0, 0, 0, 0]}
    for sample in loaded.samples:
        # Detector receives only pixels and the scalar parameter, never labels.
        boxes = [p["box"] for p in detect_threshold_pgm(sample.data, threshold)]
        labels = truth[sample.sample_id]
        tp = count_matches(labels, boxes)
        counts = (tp, len(boxes) - tp, len(labels) - tp)
        group = by_evidence[sample.evidence]
        group[0] += 1
        for index, value in enumerate(counts):
            totals[index] += value
            group[index + 1] += value
    return totals, by_evidence


def fit(
    data,
    blob_dir,
    *,
    annotations,
    expected_manifest_sha256,
    expected_protocol_sha256,
    expected_annotations_sha256,
):
    """Return deterministic model bytes; no evaluation split/labels are accepted."""
    try:
        loaded, truth = _load(
            data,
            blob_dir,
            "train",
            annotations,
            expected_manifest_sha256,
            expected_protocol_sha256,
            expected_annotations_sha256,
        )
        best = None
        selected = None
        for threshold in THRESHOLDS:
            (tp, fp, fn), _ = _counts(loaded, truth, threshold)
            denominator = 2 * tp + fp + fn
            rank = (Fraction(2 * tp, denominator) if denominator else Fraction(0), -fp, -threshold)
            if best is None or rank > best:
                best, selected = rank, threshold
        return _encode(
            {
                "version": 1,
                "baseline": BASELINE,
                "threshold": selected,
                "training_split": "train",
                "training_manifest_sha256": loaded.manifest_sha256,
                "training_annotations_sha256": expected_annotations_sha256,
                "protocol_sha256": loaded.protocol_sha256,
                "preprocessing_sha256": _digest(PREPROCESSING_BYTES),
                "search_sha256": _digest(SEARCH_BYTES),
            }
        )
    except (ValueError, TypeError, OSError, OverflowError, RecursionError, NotImplementedError):
        raise ValueError("invalid_threshold_experiment") from None


def _model(data, pin, manifest_pin, protocol_pin):
    _hash(pin)
    _require(type(data) is bytes and len(data) <= MAX_CANDIDATE_BYTES)
    _require(_digest(data) == pin)
    doc = _parse(data)
    _keys(
        doc,
        "version baseline threshold training_split training_manifest_sha256 "
        "training_annotations_sha256 protocol_sha256 preprocessing_sha256 search_sha256",
    )
    _require(type(doc["version"]) is int and doc["version"] == 1)
    _require(doc["baseline"] == BASELINE and doc["training_split"] == "train")
    _require(type(doc["threshold"]) is int and doc["threshold"] in THRESHOLDS)
    for name in (
        "training_manifest_sha256",
        "training_annotations_sha256",
        "protocol_sha256",
        "preprocessing_sha256",
        "search_sha256",
    ):
        _hash(doc[name])
    _require(doc["training_manifest_sha256"] == manifest_pin)
    _require(doc["protocol_sha256"] == protocol_pin == PROTOCOL_SHA256)
    _require(doc["preprocessing_sha256"] == _digest(PREPROCESSING_BYTES))
    _require(doc["search_sha256"] == _digest(SEARCH_BYTES))
    return doc


def evaluate(
    candidate,
    data,
    blob_dir,
    split,
    *,
    expected_candidate_sha256,
    annotations,
    expected_manifest_sha256,
    expected_protocol_sha256,
    expected_annotations_sha256,
):
    """Score a pinned scalar model on validation/test; never refit or attest training."""
    try:
        _require(type(split) is str and split in ("validation", "test"))
        model = _model(
            candidate, expected_candidate_sha256, expected_manifest_sha256, expected_protocol_sha256
        )
        loaded, truth = _load(
            data,
            blob_dir,
            split,
            annotations,
            expected_manifest_sha256,
            expected_protocol_sha256,
            expected_annotations_sha256,
        )
        counts, by_evidence = _counts(loaded, truth, model["threshold"])
        return {
            **model,
            "candidate_sha256": expected_candidate_sha256,
            "manifest_sha256": loaded.manifest_sha256,
            "annotations_sha256": expected_annotations_sha256,
            "split": split,
            "frames": len(loaded.samples),
            "metrics_scope": "supplied_obstacle_annotations",
            "metrics": _metrics(*counts),
            "metrics_by_evidence": {
                kind: {"frames": values[0], **_metrics(*values[1:])}
                for kind, values in by_evidence.items()
            },
            "rights_verified": False,
            "signatures_verified": False,
            "training_verified": False,
            "qualified": False,
        }
    except (ValueError, TypeError, OSError, OverflowError, RecursionError, NotImplementedError):
        raise ValueError("invalid_threshold_experiment") from None


def compare(
    candidate,
    data,
    blob_dir,
    split,
    *,
    expected_candidate_sha256,
    annotations,
    expected_manifest_sha256,
    expected_protocol_sha256,
    expected_annotations_sha256,
):
    """Compare three detectors on one held-out snapshot, grouped by provenance."""
    try:
        _require(type(split) is str and split in ("validation", "test"))
        model = _model(
            candidate, expected_candidate_sha256, expected_manifest_sha256, expected_protocol_sha256
        )
        loaded, truth = _load(
            data,
            blob_dir,
            split,
            annotations,
            expected_manifest_sha256,
            expected_protocol_sha256,
            expected_annotations_sha256,
        )
        provenance = _provenance_digests(data)
        # No file rereads or parameter selection between detectors. Each sees
        # only the same immutable, verified pixels; labels are used for scoring.
        detectors = (
            (BASELINE, lambda pixels: detect_threshold_pgm(pixels, model["threshold"])),
            ("classical_pgm_obstacle_v1", detect_pgm),
            ("global_pgm_obstacle_v1", detect_global_pgm),
        )
        reports = [
            _report(loaded, truth, name, detector, expected_annotations_sha256, provenance)
            for name, detector in detectors
        ]
        # Model schema v1 and metrics report schema v2 are separate. The generic
        # fixed-detector report's no-training description must not label this fit.
        reports[0].update({key: value for key, value in model.items() if key != "version"})
        reports[0].update(
            candidate_sha256=expected_candidate_sha256,
            training="pinned_train_threshold",
            training_verified=False,
            signatures_verified=False,
        )
        return {
            "version": 1,
            "comparison": "pgm_threshold_comparison_v1",
            "reports": reports,
            "rights_verified": False,
            "signatures_verified": False,
            "training_verified": False,
            "qualified": False,
        }
    except (ValueError, TypeError, OSError, OverflowError, RecursionError, NotImplementedError):
        raise ValueError("invalid_threshold_experiment") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("fit", "evaluate", "compare"):
        command = commands.add_parser(name)
        command.add_argument("manifest")
        for option in (
            "blob-dir",
            "manifest-sha256",
            "protocol-sha256",
            "annotations",
            "annotations-sha256",
        ):
            command.add_argument("--" + option, required=True)
        if name != "fit":
            for option in ("split", "candidate", "candidate-sha256"):
                command.add_argument("--" + option, required=True)
    args = parser.parse_args()
    try:
        data = _read_document(args.manifest)
        common = {
            "annotations": _read_document(args.annotations),
            "expected_manifest_sha256": args.manifest_sha256,
            "expected_protocol_sha256": args.protocol_sha256,
            "expected_annotations_sha256": args.annotations_sha256,
        }
        if args.command == "fit":
            output = fit(data, args.blob_dir, **common)
        else:
            operation = compare if args.command == "compare" else evaluate
            output = _encode(
                operation(
                    _read_document(args.candidate),
                    data,
                    args.blob_dir,
                    args.split,
                    expected_candidate_sha256=args.candidate_sha256,
                    **common,
                )
            )
    except (ValueError, OSError, AttributeError, NotImplementedError):
        print("invalid_threshold_experiment", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
