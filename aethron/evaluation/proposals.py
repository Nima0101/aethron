"""Offline comparison of PGM obstacle baselines, not accuracy qualification."""

import argparse
import hashlib
import json
import sys

from ..temporal.pixels import decode_pgm, detect_pgm
from .annotations import count_matches
from .annotations import validate as validate_annotations
from .baselines import detect_global_pgm
from .splits import _parse, _read_document, load_split

# Offline work budgets, separate from frozen runtime/evaluation thresholds.
MAX_FRAMES = 300
MAX_PIXELS = 16 * 1024 * 1024


def _metrics(tp, fp, fn):
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(tp / (tp + fp), 6) if tp + fp else None,
        "recall": round(tp / (tp + fn), 6) if tp + fn else None,
    }


def run(
    data,
    blob_dir,
    split,
    *,
    expected_manifest_sha256,
    expected_protocol_sha256,
    annotations=None,
    expected_annotations_sha256=None,
    baseline="classical_pgm_obstacle_v1",
    per_provenance=False,
):
    """Verify/load selected bytes and return only a complete aggregate report."""
    detectors = {
        "classical_pgm_obstacle_v1": detect_pgm,
        "global_pgm_obstacle_v1": detect_global_pgm,
    }
    if type(baseline) is not str or baseline not in (*detectors, "all"):
        raise ValueError("invalid_proposal_input")
    if type(per_provenance) is not bool or (per_provenance and annotations is None):
        raise ValueError("invalid_proposal_input")
    loaded = load_split(
        data,
        blob_dir,
        split,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_protocol_sha256=expected_protocol_sha256,
    )
    truth = None
    if annotations is not None or expected_annotations_sha256 is not None:
        truth = validate_annotations(
            annotations, loaded, expected_sha256=expected_annotations_sha256
        )
    try:
        if len(loaded.samples) > MAX_FRAMES:
            raise ValueError("frame_budget")
        pixels = 0
        # Reject every malformed image and the whole work budget before inference.
        for sample in loaded.samples:
            width, height, _ = decode_pgm(sample.data)
            pixels += width * height
            if pixels > MAX_PIXELS:
                raise ValueError("pixel_budget")
    except ValueError:
        raise ValueError("invalid_proposal_input") from None
    provenance_digests = None
    if per_provenance:
        # Parse the same pinned bytes; load_split already enforced the 128-source bound.
        provenance_digests = {
            row["id"]: hashlib.sha256(
                b"aethron.provenance.v1\0"
                + json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
                    "ascii"
                )
            ).hexdigest()
            for row in _parse(data)["provenance"]
        }
    names = tuple(detectors) if baseline == "all" else (baseline,)
    reports = [
        _report(
            loaded, truth, name, detectors[name], expected_annotations_sha256, provenance_digests
        )
        for name in names
    ]
    if baseline == "all":
        return {
            "version": 2 if per_provenance else 1,
            "comparison": "pgm_obstacle_baselines_v2"
            if per_provenance
            else "pgm_obstacle_baselines_v1",
            "reports": reports,
            "rights_verified": False,
            "qualified": False,
        }
    return reports[0]


def _report(loaded, truth, baseline, detector, expected_annotations_sha256, provenance_digests):
    by_provenance = {}
    tp = fp = fn = 0
    grouped = {"synthetic": [0, 0, 0], "recorded": [0, 0, 0]}
    try:
        count = with_proposals = 0
        evidence = {"synthetic": 0, "recorded": 0}
        for sample in loaded.samples:
            proposals = detector(sample.data)
            count += len(proposals)
            with_proposals += bool(proposals)
            evidence[sample.evidence] += 1
            if truth is not None:
                labels = truth[sample.sample_id]
                matches = count_matches(labels, [p["box"] for p in proposals])
                tp += matches
                fp += len(proposals) - matches
                fn += len(labels) - matches
                totals = grouped[sample.evidence]
                totals[0] += matches
                totals[1] += len(proposals) - matches
                totals[2] += len(labels) - matches
                if provenance_digests is not None:
                    digest = provenance_digests[sample.provenance_id]
                    source = by_provenance.setdefault(digest, [0, 0, 0, 0])
                    source[0] += 1
                    source[1] += matches
                    source[2] += len(proposals) - matches
                    source[3] += len(labels) - matches
    except ValueError:
        raise ValueError("invalid_proposal_input") from None
    result = {
        "version": 2 if provenance_digests is not None else 1,
        "baseline": baseline,
        "manifest_sha256": loaded.manifest_sha256,
        "protocol_sha256": loaded.protocol_sha256,
        "split": loaded.split,
        "frames": len(loaded.samples),
        "frames_with_proposals": with_proposals,
        "proposal_count": count,
        "evidence_counts": evidence,
        "training": "none",
        "accuracy_evaluated": truth is not None,
        "rights_verified": loaded.rights_verified,
        "qualified": loaded.qualified,
    }

    if truth is not None:
        result.update(
            annotations_sha256=expected_annotations_sha256,
            metrics_scope="supplied_obstacle_annotations",
            metrics=_metrics(tp, fp, fn),
            metrics_by_evidence={
                kind: {"frames": evidence[kind], **_metrics(*totals)}
                for kind, totals in grouped.items()
            },
        )
    if provenance_digests is not None:
        result["metrics_by_provenance"] = {
            digest: {"frames": totals[0], **_metrics(*totals[1:])}
            for digest, totals in sorted(by_provenance.items())
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--blob-dir", required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--protocol-sha256", required=True)
    parser.add_argument("--baseline", default="classical_pgm_obstacle_v1")
    parser.add_argument(
        "--per-provenance",
        action="store_true",
        help="emit v2 per-provenance metrics (requires pinned annotations)",
    )
    parser.add_argument("--annotations")
    parser.add_argument("--annotations-sha256")
    args = parser.parse_args()
    try:
        data = _read_document(args.manifest)
        annotations = None
        if args.annotations is not None:
            annotations = _read_document(args.annotations)
        result = run(
            data,
            args.blob_dir,
            args.split,
            expected_manifest_sha256=args.manifest_sha256,
            expected_protocol_sha256=args.protocol_sha256,
            baseline=args.baseline,
            per_provenance=args.per_provenance,
            annotations=annotations,
            expected_annotations_sha256=args.annotations_sha256,
        )
    except (OSError, ValueError, AttributeError, NotImplementedError):
        print("invalid_proposal_input", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
