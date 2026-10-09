"""Bounded split-descriptor validation, separate from rights/artifact qualification."""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass, field

MAX_BYTES = 2 * 1024 * 1024
MAX_BLOB_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
SPLITS = ("train", "validation", "test")


def _require(condition):
    if not condition:
        raise ValueError("invalid_split_manifest")


def _keys(value, names):
    _require(type(value) is dict and set(value) == set(names.split()))


def _text(value):
    _require(type(value) is str and 1 <= len(value) <= 512 and value.strip() == value)
    _require(bool(value) and all(ord(c) >= 32 and ord(c) != 127 for c in value))


def _token(value):
    _require(type(value) is str and re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", value) is not None)


def _hash(value):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _parse(data):
    _require(type(data) is bytes and len(data) <= MAX_BYTES)
    depth = 0
    quoted = escaped = False
    for char in data:
        if quoted:
            if escaped:
                escaped = False
            elif char == 92:
                escaped = True
            elif char == 34:
                quoted = False
        elif char == 34:
            quoted = True
        elif char in (91, 123):
            depth += 1
            _require(depth <= 8)
        elif char in (93, 125):
            depth -= 1
            _require(depth >= 0)
    return json.loads(
        data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda _: _require(False)
    )


def validate(data):
    """Return counts and input binding only; referenced bytes/rights are NOT verified."""
    try:
        doc = _parse(data)
        _keys(doc, "version protocol_sha256 provenance samples")
        _require(type(doc["version"]) is int and doc["version"] == 1)
        _hash(doc["protocol_sha256"])
        _require(type(doc["provenance"]) is list and 1 <= len(doc["provenance"]) <= 128)
        _require(type(doc["samples"]) is list and 3 <= len(doc["samples"]) <= 4096)
        provenance = {}
        for row in doc["provenance"]:
            _keys(row, "id source origin license evidence rights_sha256 card_sha256 allowed_splits")
            _token(row["id"])
            _require(row["id"] not in provenance)
            for name in ("source", "origin", "license"):
                _text(row[name])
            _require(type(row["evidence"]) is str and row["evidence"] in ("synthetic", "recorded"))
            for name in ("rights_sha256", "card_sha256"):
                _hash(row[name])
            allowed = row["allowed_splits"]
            _require(type(allowed) is list and 1 <= len(allowed) <= 3)
            _require(all(type(s) is str and s in SPLITS for s in allowed))
            _require(len(set(allowed)) == len(allowed))
            provenance[row["id"]] = allowed
        counts = dict.fromkeys(SPLITS, 0)
        ids, artifacts, used = set(), set(), set()
        content_splits, session_splits = {}, {}
        for row in doc["samples"]:
            _keys(row, "id split session_sha256 artifact_sha256 source_sha256 provenance_id")
            _token(row["id"])
            _token(row["provenance_id"])
            _require(row["id"] not in ids)
            ids.add(row["id"])
            split = row["split"]
            _require(type(split) is str and split in SPLITS)
            _require(row["provenance_id"] in provenance)
            _require(split in provenance[row["provenance_id"]])
            used.add(row["provenance_id"])
            for name in ("artifact_sha256", "source_sha256", "session_sha256"):
                _hash(row[name])
            # Raw and derived hashes share a namespace so aliases cannot hide leakage.
            for name in ("artifact_sha256", "source_sha256"):
                digest = row[name]
                _require(content_splits.setdefault(digest, split) == split)
            _require(session_splits.setdefault(row["session_sha256"], split) == split)
            _require(row["artifact_sha256"] not in artifacts)
            artifacts.add(row["artifact_sha256"])
            counts[split] += 1
        _require(all(counts.values()) and used == set(provenance))
        return {
            "version": 1,
            "manifest_sha256": hashlib.sha256(data).hexdigest(),
            "protocol_sha256": doc["protocol_sha256"],
            "counts": counts,
            "qualified": False,
            "artifacts_verified": False,
            "rights_verified": False,
        }
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise ValueError("invalid_split_manifest") from None


def _file_state(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _verify_blob(root_fd, digest, remaining, *, retain=False):
    # NONBLOCK prevents a substituted FIFO from hanging before fstat rejects it.
    fd = os.open(digest, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
    try:
        before = os.fstat(fd)
        _require(stat.S_ISREG(before.st_mode))
        _require(0 <= before.st_size <= min(MAX_BLOB_BYTES, remaining))
        hashed = hashlib.sha256()
        chunks = [] if retain else None
        size = 0
        while True:
            chunk = os.read(fd, min(65536, before.st_size - size + 1))
            if not chunk:
                break
            size += len(chunk)
            _require(size <= before.st_size)
            hashed.update(chunk)
            if chunks is not None:
                chunks.append(chunk)
        after = os.fstat(fd)
        current = os.stat(digest, dir_fd=root_fd, follow_symlinks=False)
        _require(stat.S_ISREG(current.st_mode))
        _require(_file_state(before) == _file_state(after) == _file_state(current))
        _require(size == before.st_size and hashed.hexdigest() == digest)
        return size, b"".join(chunks) if chunks is not None else None
    finally:
        os.close(fd)


def _check_artifacts(data, blob_dir, retain_split=None):
    result = validate(data)  # Reject invalid descriptors before any filesystem access.
    doc = _parse(data)
    references = {"protocol": [doc["protocol_sha256"]]}
    for role in ("card", "rights"):
        references[role] = [row[role + "_sha256"] for row in doc["provenance"]]
    for role in ("source", "artifact"):
        references[role] = [row[role + "_sha256"] for row in doc["samples"]]
    digests = sorted({digest for values in references.values() for digest in values})
    selected = {row["artifact_sha256"] for row in doc["samples"] if row["split"] == retain_split}
    payloads = {}
    try:
        _require(os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd)
        # Remove trailing separators/dot components that would bypass leaf NOFOLLOW.
        root_path = os.path.normpath(blob_dir)
        root_fd = os.open(root_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            total = 0
            for digest in digests:
                size, payload = _verify_blob(
                    root_fd, digest, MAX_TOTAL_BYTES - total, retain=digest in selected
                )
                total += size
                if payload is not None:
                    payloads[digest] = payload
        finally:
            os.close(root_fd)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        raise ValueError("invalid_split_artifacts") from None
    report = dict(
        result,
        artifacts_verified=True,
        verified_blobs=len(digests),
        verified_bytes=total,
        verified_references={role: len(values) for role, values in references.items()},
    )

    return report, doc, payloads


def verify_artifacts(data, blob_dir):
    """Match referenced bytes, trusting the root parent; never approve rights/signatures."""
    return _check_artifacts(data, blob_dir)[0]


@dataclass(frozen=True)
class LoadedSample:
    sample_id: str
    artifact_sha256: str
    source_sha256: str
    session_sha256: str
    provenance_id: str
    evidence: str
    data: bytes = field(repr=False)


@dataclass(frozen=True)
class LoadedSplit:
    manifest_sha256: str
    protocol_sha256: str
    split: str
    samples: tuple
    rights_verified: bool = field(default=False, init=False)
    qualified: bool = field(default=False, init=False)


def load_split(data, blob_dir, split, *, expected_manifest_sha256, expected_protocol_sha256):
    """Load immutable selected samples after fresh verification of ALL references.

    Pins come from caller-controlled evaluation configuration, not an earlier
    report. No paths or open descriptors escape; no partial result is returned.
    """
    binding = validate(data)
    try:
        _require(type(split) is str and split in SPLITS)
        _hash(expected_manifest_sha256)
        _hash(expected_protocol_sha256)
        _require(binding["manifest_sha256"] == expected_manifest_sha256)
        _require(binding["protocol_sha256"] == expected_protocol_sha256)
    except ValueError:
        raise ValueError("invalid_split_selection") from None
    report, doc, payloads = _check_artifacts(data, blob_dir, split)
    evidence = {row["id"]: row["evidence"] for row in doc["provenance"]}
    samples = tuple(
        LoadedSample(
            row["id"],
            row["artifact_sha256"],
            row["source_sha256"],
            row["session_sha256"],
            row["provenance_id"],
            evidence[row["provenance_id"]],
            payloads[row["artifact_sha256"]],
        )
        for row in doc["samples"]
        if row["split"] == split
    )
    return LoadedSplit(report["manifest_sha256"], report["protocol_sha256"], split, samples)


def _read_document(path):
    """Read one bounded regular document; CLI callers retain their own fixed errors."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        _require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode))
        data = stream.read(MAX_BYTES + 1)
    _require(len(data) <= MAX_BYTES)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--blob-dir", help="Directory of SHA-256-named local blobs")
    args = parser.parse_args()
    try:
        data = _read_document(args.manifest)
        result = verify_artifacts(data, args.blob_dir) if args.blob_dir else validate(data)
    except (OSError, ValueError, AttributeError, NotImplementedError):
        print("invalid_split_manifest", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
