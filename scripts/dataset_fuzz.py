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
from aethron.evaluation.splits import _read_document, load_split
from aethron.evaluation.splits import validate as validate_manifest
from aethron.evaluation.synthetic import generate

TARGETS = ("manifest", "annotations", "pixels")
ERRORS = dict(zip(TARGETS, ("invalid_split_manifest", "invalid_annotations", "invalid_input")))


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


def run(*, cases=300, seconds=5, seed=472):
    if (
        type(cases) is not int
        or not 1 <= cases <= 10000
        or type(seconds) not in (int, float)
        or not 0 < seconds <= 60
        or type(seed) is not int
        or not 0 <= seed < 2**32
    ):
        raise ValueError("invalid_fuzz_input")
    try:
        sources = _sources()
        with tempfile.TemporaryDirectory(prefix="aethron-dataset-fuzz-") as temporary:
            root = Path(temporary) / "fixture"
            pins = generate(root)
            manifest = _read_document(root / "manifest.json")
            loaded = load_split(
                manifest,
                root / "blobs",
                "test",
                expected_manifest_sha256=pins["manifest_sha256"],
                expected_protocol_sha256=pins["protocol_sha256"],
            )
            seeds = (
                manifest,
                _read_document(root / "annotations-test.json"),
                loaded.samples[0].data,
            )
    except (OSError, ValueError, AttributeError, NotImplementedError):
        raise ValueError("invalid_fuzz_input") from None
    counts = {name: {"accepted": 0, "rejected": 0, "controls": 0} for name in TARGETS}
    rng, stream = random.Random(seed), hashlib.sha256()
    failure, completed = None, 0
    started = time.monotonic()
    for index in range(cases):
        if time.monotonic() - started >= seconds:
            break
        target = TARGETS[index % 3]
        mode = (index // 3) % 5
        data = _mutate(seeds[index % 3], mode, rng)
        stream.update(target.encode() + b"\0" + len(data).to_bytes(8, "big") + data)
        completed += 1
        reason = None
        try:
            value = _call(target, data, loaded)
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
        "version": 1,
        "seed": seed,
        "requested_cases": cases,
        "cases": completed,
        "seconds_limit": seconds,
        "elapsed_s": round(elapsed, 6),
        "status": status,
        "counts": counts,
        "failure": failure,
        "case_stream_sha256": stream.hexdigest(),
        "input_sha256": {name: _digest(data) for name, data in zip(TARGETS, seeds)},
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
    args = parser.parse_args()
    try:
        result = run(cases=args.cases, seconds=args.seconds, seed=args.seed)
    except ValueError:
        print("invalid_fuzz_input", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["all_succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
