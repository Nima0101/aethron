"""Seeded, bounded offline dataset API fuzzing; not release or field qualification."""

import argparse
import hashlib
import json
import random
import sys
import tempfile
import time
from pathlib import Path

import aethron
from aethron.evaluation.annotations import count_matches
from aethron.evaluation.annotations import validate as validate_annotations
from aethron.evaluation.baselines import detect_global_pgm
from aethron.evaluation.candidates import verify_artifacts as verify_candidate
from aethron.evaluation.proposals import run as run_proposals
from aethron.evaluation.splits import _filesystem_supported, _read_document, load_split
from aethron.evaluation.splits import validate as validate_manifest
from aethron.evaluation.synthetic import generate

TARGETS = ("manifest", "annotations", "pixels")
REPORT_TARGETS = ("report_annotations", "report_pin", "report_source")
CANDIDATE_TARGETS = ("candidate_descriptor", "candidate_pin", "candidate_artifact")
OVERSIZED_BLOB = b"sparse_blob_bytes:67108865"
ERRORS = dict(zip(TARGETS, ("invalid_split_manifest", "invalid_annotations", "invalid_input")))
ERRORS.update(
    zip(REPORT_TARGETS, ("invalid_annotations", "invalid_annotations", "invalid_split_artifacts"))
)

ERRORS.update(dict.fromkeys(CANDIDATE_TARGETS, "invalid_model_candidate"))


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _sources():
    root = Path(aethron.__file__).parent
    files = {"scripts/dataset_fuzz.py": Path(__file__)}
    for path in root.rglob("*.py"):
        if len(files) >= 256:
            raise ValueError("invalid_fuzz_input")
        files["aethron/" + path.relative_to(root).as_posix()] = path
    result, total = {}, 0
    for name, path in sorted(files.items()):
        data = _read_document(path)
        total += len(data)
        if total > 16 * 1024 * 1024:
            raise ValueError("invalid_fuzz_input")
        result[name] = _digest(data)
    return result


def _mutate(data, mode, rng):
    if mode == 0:
        return data
    if mode == 1:
        value = bytearray(data)
        for _ in range(rng.randint(1, 8)):
            value[rng.randrange(len(value))] = rng.randrange(256)
        return bytes(value)
    if mode == 2:
        return data[: rng.randrange(len(data))]
    if mode == 3:
        return data + b"\xff"
    return rng.choice((b"null", b"NaN", b"[" * 9 + b"]" * 9, b'{"version":1,"version":1}'))


def _annotation_variant(data, variant):
    # Only validated, owned seed labels enter here; malformed mutations use _mutate.
    doc = json.loads(data)
    for row in doc["samples"]:
        if variant == 0:
            row["boxes"] = []
        elif variant == 1:
            row["boxes"] = [[0, 0, 0.125, 0.125]]
        else:
            row["boxes"].append([0, 0, 0.125, 0.125])
    return json.dumps(doc, sort_keys=True).encode()


def _call(target, data, loaded):
    if target == "manifest":
        return validate_manifest(data)
    if target == "annotations":
        # Rebind mutated bytes so structure is exercised beyond the digest gate.
        return validate_annotations(data, loaded, expected_sha256=_digest(data))
    return detect_global_pgm(data)


def _ensure(condition):
    if not condition:
        raise RuntimeError("invalid_fuzz_result")


def _inspect(target, data, value, loaded, control):
    if target == "manifest":
        _ensure(value["manifest_sha256"] == _digest(data))
        _ensure(
            all(
                value[key] is False
                for key in ("qualified", "rights_verified", "artifacts_verified")
            )
        )
        _ensure(set(value["counts"]) == {"train", "validation", "test"})
        _ensure(all(type(n) is int and n > 0 for n in value["counts"].values()))
        _ensure(sum(value["counts"].values()) <= 4096)
        if control:
            _ensure(value["counts"] == {"train": 3, "validation": 3, "test": 3})
    elif target == "annotations":
        _ensure(set(value) == {row.sample_id for row in loaded.samples})
        for boxes in value.values():
            _ensure(count_matches(boxes, boxes) == len(boxes))
        if control:
            _ensure(
                value
                == {
                    "test_match": [[0.375, 0.375, 0.25, 0.25]],
                    "test_miss": [[0.375, 0.375, 0.25, 0.25]],
                    "test_false_positive": [],
                }
            )
    else:
        _ensure(type(value) is list and len(value) <= 32)
        for row in value:
            _ensure(set(row) == {"class", "box", "score", "variance", "range_m"})
            _ensure(
                row["class"] == "obstacle"
                and row["score"] == 0.6
                and row["variance"] == 0.0001
                and row["range_m"] is None
            )
            _ensure(count_matches([row["box"]], [row["box"]]) == 1)
        if control:
            _ensure([row["box"] for row in value] == [[0.375, 0.375, 0.25, 0.25]])


def _report_fixture(manifest, labels, root, pins):
    # Original synthetic declarations: selected match/negative, selected miss, unselected.
    doc, annotation = json.loads(manifest), json.loads(labels)
    template = doc["provenance"][0]
    doc["provenance"] = [dict(template, id=name) for name in ("supported", "missed", "unselected")]
    for row in doc["samples"]:
        row["provenance_id"] = (
            "unselected"
            if row["split"] != "test"
            else "missed"
            if row["id"] == "test_miss"
            else "supported"
        )
    manifest = json.dumps(doc, sort_keys=True).encode()
    pins = dict(pins, manifest_sha256=_digest(manifest))
    annotation["manifest_sha256"] = pins["manifest_sha256"]
    labels = json.dumps(annotation, sort_keys=True).encode()
    groups = {
        row["id"]: _digest(
            b"aethron.provenance.v1\0"
            + json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
                "ascii"
            )
        )
        for row in doc["provenance"]
    }
    return (
        manifest,
        labels,
        pins,
        {
            "manifest": manifest,
            "labels": labels,
            "root": root,
            "pins": pins,
            "groups": groups,
        },
    )


def _call_report(target, data, loaded, context):
    labels = data if target == "report_annotations" else context["labels"]
    # Invalid bytes become invalid pin text for the real API to reject.
    pin = data.decode("ascii", errors="replace") if target == "report_pin" else _digest(labels)
    source = context["root"] / "blobs" / loaded.samples[0].artifact_sha256
    try:
        if target == "report_source":
            source.write_bytes(data)
        return run_proposals(
            context["manifest"],
            context["root"] / "blobs",
            "test",
            expected_manifest_sha256=context["pins"]["manifest_sha256"],
            expected_protocol_sha256=context["pins"]["protocol_sha256"],
            annotations=labels,
            expected_annotations_sha256=pin,
            baseline="all",
            per_provenance=True,
        )
    finally:
        if target == "report_source":
            source.write_bytes(loaded.samples[0].data)


def _stats(totals):
    tp, fp, fn = totals
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(tp / (tp + fp), 6) if tp + fp else None,
        "recall": round(tp / (tp + fn), 6) if tp + fn else None,
    }


def _inspect_report(target, data, value, loaded, context):
    labels = data if target == "report_annotations" else context["labels"]
    truth = validate_annotations(labels, loaded, expected_sha256=_digest(labels))
    expected = {
        "version": 2,
        "comparison": "pgm_obstacle_baselines_v2",
        "reports": [],
        "rights_verified": False,
        "qualified": False,
    }
    for baseline in ("classical_pgm_obstacle_v1", "global_pgm_obstacle_v1"):
        # Hand-established predictions on these three original 8x8 fixtures.
        boxes = {
            "test_match": [[0.375, 0.375, 0.25, 0.25]],
            "test_miss": [],
            "test_false_positive": [[0, 0, 1, 1]] if baseline.startswith("global") else [],
        }
        grouped, pooled = {}, [0, 0, 0]
        for sample in loaded.samples:
            proposals, annotations = boxes[sample.sample_id], truth[sample.sample_id]
            tp = count_matches(annotations, proposals)
            counts = [tp, len(proposals) - tp, len(annotations) - tp]
            key = context["groups"][sample.provenance_id]
            group = grouped.setdefault(key, [0, 0, 0, 0])
            group[0] += 1
            for i, count in enumerate(counts):
                pooled[i] += count
                group[i + 1] += count
        report = {
            "version": 2,
            "baseline": baseline,
            "manifest_sha256": loaded.manifest_sha256,
            "protocol_sha256": loaded.protocol_sha256,
            "annotations_sha256": _digest(labels),
            "split": "test",
            "frames": 3,
            "frames_with_proposals": sum(bool(b) for b in boxes.values()),
            "proposal_count": sum(len(b) for b in boxes.values()),
            "evidence_counts": {"synthetic": 3, "recorded": 0},
            "training": "none",
            "accuracy_evaluated": True,
            "rights_verified": False,
            "qualified": False,
            "metrics_scope": "supplied_obstacle_annotations",
            "metrics": _stats(pooled),
            "metrics_by_evidence": {
                "synthetic": {"frames": 3, **_stats(pooled)},
                "recorded": {"frames": 0, **_stats([0, 0, 0])},
            },
            "metrics_by_provenance": {
                key: {"frames": v[0], **_stats(v[1:])} for key, v in grouped.items()
            },
        }
        expected["reports"].append(report)
    # Closed output comparison also detects private fields and bool/numeric substitutions.
    _ensure(
        json.dumps(value, sort_keys=True, allow_nan=False)
        == json.dumps(expected, sort_keys=True, allow_nan=False)
    )


def _candidate_fixture(manifest, root, pins):
    doc = {
        "version": 1,
        "task": "obstacle_proposals",
        "format": "opaque",
        "protocol_sha256": pins["protocol_sha256"],
        "training_manifest_sha256": pins["manifest_sha256"],
        "training_split": "train",
    }
    for role in ("artifact", "preprocessing", "card", "rights"):
        payload = ("original candidate fuzz fixture: " + role).encode()
        doc[role + "_sha256"] = _digest(payload)
        with (root / "blobs" / _digest(payload)).open("xb") as stream:
            stream.write(payload)
    data = json.dumps(doc, sort_keys=True).encode()
    artifact = (root / "blobs" / doc["artifact_sha256"]).read_bytes()
    blobs = list((root / "blobs").iterdir())
    expected = dict(
        doc,
        candidate_sha256=_digest(data),
        training_samples=3,
        artifacts_verified=True,
        training_verified=False,
        preprocessing_verified=False,
        rights_verified=False,
        signatures_verified=False,
        qualified=False,
        verified_blob_reads=len(blobs),
        verified_bytes=sum(p.stat().st_size for p in blobs),
    )
    return (data, _digest(data).encode("ascii"), artifact), {
        "kind": "candidate",
        "manifest": manifest,
        "root": root,
        "pins": pins,
        "descriptor": data,
        "artifact": artifact,
        "expected": expected,
    }


def _call_candidate(target, data, context):
    descriptor = data if target == "candidate_descriptor" else context["descriptor"]
    pin = (
        data.decode("ascii", errors="replace") if target == "candidate_pin" else _digest(descriptor)
    )
    path = context["root"] / "blobs" / context["expected"]["artifact_sha256"]
    try:
        if target == "candidate_artifact":
            if data == OVERSIZED_BLOB:
                with path.open("wb") as stream:
                    stream.truncate(64 * 1024 * 1024 + 1)
            else:
                path.write_bytes(data)
        return verify_candidate(
            descriptor,
            context["manifest"],
            context["root"] / "blobs",
            expected_candidate_sha256=pin,
            expected_manifest_sha256=context["pins"]["manifest_sha256"],
            expected_protocol_sha256=context["pins"]["protocol_sha256"],
        )
    finally:
        if target == "candidate_artifact":
            path.write_bytes(context["artifact"])


def _inspect_candidate(target, data, value, context):
    descriptor = data if target == "candidate_descriptor" else context["descriptor"]
    # These mutations may change serialization but do not introduce other valid fixtures.
    _ensure(json.loads(descriptor) == json.loads(context["descriptor"]))
    expected = dict(context["expected"], candidate_sha256=_digest(descriptor))
    _ensure(
        json.dumps(value, sort_keys=True, allow_nan=False)
        == json.dumps(expected, sort_keys=True, allow_nan=False)
    )


def run(*, cases=300, seconds=5, seed=472, reports=False, candidates=False):
    if (
        not _filesystem_supported(write=True)
        or type(candidates) is not bool
        or (candidates and reports)
        or type(reports) is not bool
        or type(cases) is not int
        or not 1 <= cases <= 10000
        or type(seconds) not in (int, float)
        or not 0 < seconds <= 60
        or type(seed) is not int
        or not 0 <= seed < 2**32
    ):
        raise ValueError("invalid_fuzz_input")
    try:
        owned = tempfile.TemporaryDirectory(prefix="aethron-dataset-fuzz-")
        with owned as temporary:
            try:
                sources = _sources()
                root = Path(temporary) / "fixture"
                pins = generate(root)
                manifest = _read_document(root / "manifest.json")
                labels = _read_document(root / "annotations-test.json")
                context = None
                if reports:
                    manifest, labels, pins, context = _report_fixture(manifest, labels, root, pins)
                loaded = load_split(
                    manifest,
                    root / "blobs",
                    "test",
                    expected_manifest_sha256=pins["manifest_sha256"],
                    expected_protocol_sha256=pins["protocol_sha256"],
                )
                seeds = (
                    (labels, _digest(labels).encode("ascii"), loaded.samples[0].data)
                    if reports
                    else (manifest, labels, loaded.samples[0].data)
                )
                if candidates:
                    seeds, context = _candidate_fixture(manifest, root, pins)
            except (OSError, ValueError, AttributeError, NotImplementedError):
                raise ValueError("invalid_fuzz_input") from None
            # Report/candidate cases need fresh blob verification throughout their owned lifetime.
            if reports or candidates:
                return _campaign(cases, seconds, seed, loaded, seeds, sources, context)
        return _campaign(cases, seconds, seed, loaded, seeds, sources, None)
    except OSError:
        raise ValueError("invalid_fuzz_input") from None


def _campaign(cases, seconds, seed, loaded, seeds, sources, context):
    candidate_mode = context is not None and context.get("kind") == "candidate"
    targets = (
        CANDIDATE_TARGETS if candidate_mode else REPORT_TARGETS if context is not None else TARGETS
    )
    counts = {name: {"accepted": 0, "rejected": 0, "controls": 0} for name in targets}
    rng, stream = random.Random(seed), hashlib.sha256()
    failure, completed = None, 0
    started = time.monotonic()
    for index in range(cases):
        if time.monotonic() - started >= seconds:
            break
        target = targets[index % 3]
        mode = (index // 3) % 5
        data = (
            _annotation_variant(seeds[0], (index // 15) % 3)
            if target == "report_annotations" and mode == 4
            else _mutate(seeds[index % 3], mode, rng)
        )
        if target == "candidate_artifact" and mode == 4:
            data = OVERSIZED_BLOB
        stream.update(target.encode() + b"\0" + len(data).to_bytes(8, "big") + data)
        completed += 1
        reason = None
        try:
            value = (
                _call_candidate(target, data, context)
                if candidate_mode
                else _call_report(target, data, loaded, context)
                if context is not None
                else _call(target, data, loaded)
            )
        except ValueError as exc:
            if str(exc) != ERRORS[target]:
                reason = "unexpected_exception"
            elif mode == 0:
                reason = "control_rejected"
            else:
                counts[target]["rejected"] += 1
        except Exception:
            reason = "unexpected_exception"
        else:
            try:
                if candidate_mode:
                    _inspect_candidate(target, data, value, context)
                elif context is not None:
                    _inspect_report(target, data, value, loaded, context)
                else:
                    _inspect(target, data, value, loaded, mode == 0)
            except Exception:
                reason = "unexpected_result"
            else:
                counts[target]["accepted"] += 1
                counts[target]["controls"] += mode == 0
        if reason:
            failure = {"index": index, "target": target, "sha256": _digest(data), "reason": reason}
            break
    elapsed = time.monotonic() - started
    try:
        stable = _sources() == sources
    except (OSError, ValueError, AttributeError, NotImplementedError):
        stable = False
    status = "failure" if failure else "time_limit" if elapsed >= seconds else "case_limit"
    return {
        "version": 3 if candidate_mode else 2 if context is not None else 1,
        "seed": seed,
        "requested_cases": cases,
        "cases": completed,
        "seconds_limit": seconds,
        "elapsed_s": round(elapsed, 6),
        "status": status,
        "counts": counts,
        "failure": failure,
        "case_stream_sha256": stream.hexdigest(),
        "input_sha256": {name: _digest(data) for name, data in zip(targets, seeds)},
        "source_sha256": sources,
        "source_stable": stable,
        "qualified": False,
        "all_succeeded": failure is None and stable and completed == cases and elapsed < seconds,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=300)
    parser.add_argument("--seconds", type=float, default=5)
    parser.add_argument("--seed", type=int, default=472)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--reports", action="store_true", help="fuzz v2 report orchestration")
    modes.add_argument("--candidates", action="store_true", help="fuzz offline candidate checks")
    args = parser.parse_args()
    try:
        result = run(
            cases=args.cases,
            seconds=args.seconds,
            seed=args.seed,
            reports=args.reports,
            candidates=args.candidates,
        )
    except ValueError:
        print("invalid_fuzz_input", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["all_succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
