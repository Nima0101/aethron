"""Versioned obstacle-only annotations and offline matching; no temporal identities."""

import hashlib

from ..temporal.math import assignment, iou
from .splits import _hash, _keys, _parse, _require, _token

# Exact UTF-8 protocol bytes including trailing newline. Change semantics only
# with a new protocol version; existing dataset/protocol freezes stay unchanged.
PROTOCOL_BYTES = (
    b'{"version":1,"task":"obstacle_proposals","iou_min":0.3,'
    b'"matching":"max_cardinality_then_iou","box":"normalized_xywh",'
    b'"max_boxes_per_frame":64}\n'
)
PROTOCOL_SHA256 = hashlib.sha256(PROTOCOL_BYTES).hexdigest()


def _boxes(value, *, unique=True):
    _require(type(value) is list and len(value) <= 64)
    for box in value:
        _require(type(box) is list and len(box) == 4)
        _require(all(type(v) in (int, float) and 0 <= v <= 1 for v in box))
        _require(box[2] > 0 and box[3] > 0)
        _require(box[0] + box[2] <= 1 and box[1] + box[3] <= 1)
    if unique:
        _require(len({tuple(box) for box in value}) == len(value))


def validate(data, loaded, *, expected_sha256):
    """Bind complete labels to exact loaded sample bytes; never approve label quality."""
    try:
        _hash(expected_sha256)
        doc = _parse(data)
        _require(hashlib.sha256(data).hexdigest() == expected_sha256)
        _keys(doc, "version manifest_sha256 protocol_sha256 split samples")
        _require(type(doc["version"]) is int and doc["version"] == 1)
        _require(doc["manifest_sha256"] == loaded.manifest_sha256)
        _require(doc["protocol_sha256"] == loaded.protocol_sha256 == PROTOCOL_SHA256)
        _require(doc["split"] == loaded.split)
        _require(type(doc["samples"]) is list and len(doc["samples"]) == len(loaded.samples))
        selected = {sample.sample_id: sample.artifact_sha256 for sample in loaded.samples}
        truth = {}
        for row in doc["samples"]:
            _keys(row, "sample_id artifact_sha256 boxes")
            _token(row["sample_id"])
            _hash(row["artifact_sha256"])
            _require(row["sample_id"] not in truth)
            _require(selected.get(row["sample_id"]) == row["artifact_sha256"])
            _boxes(row["boxes"])
            truth[row["sample_id"]] = row["boxes"]
        _require(set(truth) == set(selected))
        return truth
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise ValueError("invalid_annotations") from None


def count_matches(truth, proposals):
    """Inclusive IoU0.3: maximize match count, then total IoU, with deterministic ties."""
    try:
        _boxes(truth)
        _boxes(proposals, unique=False)
        # At most64 rows: losing one match costs65, more than the total possible
        # IoU-cost difference. Ineligible edges cost130 and cannot beat a dummy.
        costs = [
            [1 - iou(g, p) if iou(g, p) >= 0.3 else 130.0 for p in proposals] + [65.0] * len(truth)
            for g in truth
        ]
        return sum(j < len(proposals) and costs[i][j] < 65 for i, j in assignment(costs))
    except (ValueError, TypeError, OverflowError):
        raise ValueError("invalid_annotations") from None
