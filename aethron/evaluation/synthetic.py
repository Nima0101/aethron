"""Reproducible original PGM software fixtures, never a held-out accuracy dataset."""

import argparse
import hashlib
import json
import os
import sys

from .annotations import PROTOCOL_BYTES, PROTOCOL_SHA256
from .splits import SPLITS, _filesystem_supported


def _json(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _dataset():
    blobs = {}

    def blob(data):
        digest = _digest(data)
        blobs[digest] = data
        return digest

    blob(PROTOCOL_BYTES)
    rights = blob(b"Original AETHRON generated synthetic pixels; GPL-3.0-only. No external data.\n")
    card = blob(
        _json(
            {
                "version": 1,
                "generator": "synthetic_pgm_v1",
                "license": "GPL-3.0-only",
                "origin": "AETHRON original deterministic pixel fixtures",
                "training": "none",
                "intended_use": "Offline software regression and CLI demonstration",
                "limitations": "Related synthetic variants, not independent accuracy evidence. No semantic or physical qualification.",
                "forbidden_use": "No identity, surveillance history, actuation or field safety claims",
            }
        )
    )
    doc = {
        "version": 1,
        "protocol_sha256": PROTOCOL_SHA256,
        "provenance": [
            {
                "id": "synthetic_pgm_v1",
                "source": "Original deterministic PGM generation",
                "origin": "AETHRON",
                "license": "GPL-3.0-only",
                "evidence": "synthetic",
                "rights_sha256": rights,
                "card_sha256": card,
                "allowed_splits": list(SPLITS),
            }
        ],
        "samples": [],
    }
    truth = {split: [] for split in SPLITS}
    for index, split in enumerate(SPLITS):
        session = _digest(f"synthetic_pgm_v1:{split}".encode())
        for case, background in (("match", 200), ("miss", 180), ("false_positive", 100)):
            pixels = bytearray([background + index] * 64)
            boxes = []
            if case != "false_positive":
                for point in (27, 28, 35, 36):
                    pixels[point] = 0 if case == "match" else 255
                boxes = [[0.375, 0.375, 0.25, 0.25]]
            digest = blob(b"P5\n8 8\n255\n" + bytes(pixels))
            sample_id = split + "_" + case
            doc["samples"].append(
                {
                    "id": sample_id,
                    "split": split,
                    "session_sha256": session,
                    "source_sha256": digest,
                    "artifact_sha256": digest,
                    "provenance_id": "synthetic_pgm_v1",
                }
            )
            truth[split].append({"sample_id": sample_id, "artifact_sha256": digest, "boxes": boxes})
    manifest = _json(doc)
    annotations = {
        split: _json(
            {
                "version": 1,
                "manifest_sha256": _digest(manifest),
                "protocol_sha256": PROTOCOL_SHA256,
                "split": split,
                "samples": truth[split],
            }
        )
        for split in SPLITS
    }
    pins = {
        "version": 1,
        "generator": "synthetic_pgm_v1",
        "evidence": "synthetic",
        "training": "none",
        "qualified": False,
        "rights_verified": False,
        "manifest_sha256": _digest(manifest),
        "protocol_sha256": PROTOCOL_SHA256,
        "annotations_sha256": {split: _digest(data) for split, data in annotations.items()},
    }
    return blobs, manifest, annotations, pins


def _write(directory_fd, name, data):
    fd = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def generate(output_dir):
    """Create a NEW directory under a trusted parent; publish only complete pins."""
    try:
        if not _filesystem_supported(write=True):
            raise ValueError("invalid_fixture_output")
        blobs, manifest, annotations, pins = _dataset()
        os.mkdir(output_dir, 0o700)  # Even empty existing directories are rejected.
        root_fd = os.open(output_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.mkdir("blobs", 0o700, dir_fd=root_fd)
            blobs_fd = os.open(
                "blobs", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
            )
            try:
                for digest, data in sorted(blobs.items()):
                    _write(blobs_fd, digest, data)
            finally:
                os.close(blobs_fd)
            _write(root_fd, "manifest.json", manifest)
            for split, data in annotations.items():
                _write(root_fd, f"annotations-{split}.json", data)
            _write(root_fd, ".pins.pending", _json(pins))
            # Hard-link publication is atomic and never replaces an existing entry.
            os.link(
                ".pins.pending",
                "pins.json",
                src_dir_fd=root_fd,
                dst_dir_fd=root_fd,
                follow_symlinks=False,
            )
            os.unlink(".pins.pending", dir_fd=root_fd)
        finally:
            os.close(root_fd)
        return pins
    except (OSError, ValueError, TypeError, AttributeError, NotImplementedError):
        # Preserve incomplete output for inspection; never recursively delete a path.
        raise ValueError("invalid_fixture_output") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir")
    args = parser.parse_args()
    try:
        pins = generate(args.output_dir)
    except ValueError:
        print("invalid_fixture_output", file=sys.stderr)
        return 2
    print(json.dumps(pins, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
