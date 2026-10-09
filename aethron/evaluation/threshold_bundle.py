"""Export pinned experimental scalar bytes and dependencies; no execution approval."""

import argparse
import os
import stat
import sys

from . import candidates, threshold
from .splits import (
    MAX_BYTES,
    MAX_TOTAL_BYTES,
    _file_state,
    _filesystem_supported,
    _hash,
    _parse,
    _read_document,
    _require,
    _verify_blob,
)
from .threshold import _digest, _encode


def _write(directory_fd, name, data):
    fd = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def _completion_pins(candidate, model, manifest, protocol):
    return {
        "version": 1,
        "bundle": "experimental_pgm_threshold_bundle_v1",
        "candidate_sha256": candidate,
        "model_sha256": model,
        "manifest_sha256": manifest,
        "protocol_sha256": protocol,
        "search_sha256": _digest(threshold.SEARCH_BYTES),
        "rights_verified": False,
        "signatures_verified": False,
        "training_verified": False,
        "qualified": False,
    }


def _read_at(root_fd, name, limit):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root_fd)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        _require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit)
        data = stream.read(limit + 1)
        current = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        _require(
            _file_state(before) == _file_state(os.fstat(stream.fileno())) == _file_state(current)
        )
        _require(len(data) == before.st_size)
    return data


def verify(
    bundle_dir, *, expected_candidate_sha256, expected_manifest_sha256, expected_protocol_sha256
):
    """Verify a relocated, quiescent bundle below a trusted parent; never execute it.

    Completion bytes are checked against caller-supplied pins, not trusted as
    configuration. These integrity checks do not authenticate the caller's pins.
    """
    try:
        bindings = {
            "expected_candidate_sha256": expected_candidate_sha256,
            "expected_manifest_sha256": expected_manifest_sha256,
            "expected_protocol_sha256": expected_protocol_sha256,
        }
        for pin in bindings.values():
            _hash(pin)
        root = os.path.normpath(bundle_dir)
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            before = os.fstat(root_fd)
            data = _read_at(root_fd, "candidate.json", candidates.MAX_CANDIDATE_BYTES)
            manifest = _read_at(root_fd, "manifest.json", MAX_BYTES)
            completion = _read_at(root_fd, "pins.json", candidates.MAX_CANDIDATE_BYTES)
            report = candidates.validate(data, manifest, **bindings)
            pins = _completion_pins(
                expected_candidate_sha256,
                report["artifact_sha256"],
                expected_manifest_sha256,
                expected_protocol_sha256,
            )
            _require(completion == _encode(pins))
            report = candidates.verify_artifacts(
                data, manifest, os.path.join(root, "blobs"), **bindings
            )
            blob_fd = os.open("blobs", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                total = report["verified_bytes"]
                size, model = _verify_blob(
                    blob_fd,
                    pins["model_sha256"],
                    min(candidates.MAX_CANDIDATE_BYTES, MAX_TOTAL_BYTES - total),
                    retain=True,
                )
                total += size
                threshold._model(
                    model, pins["model_sha256"], expected_manifest_sha256, expected_protocol_sha256
                )
                _require(report["preprocessing_sha256"] == _digest(threshold.PREPROCESSING_BYTES))
                size, _ = _verify_blob(
                    blob_fd, pins["search_sha256"], min(MAX_BYTES, MAX_TOTAL_BYTES - total)
                )
                total += size
            finally:
                os.close(blob_fd)
            _require(_file_state(before) == _file_state(os.stat(root, follow_symlinks=False)))
        finally:
            os.close(root_fd)
        return dict(
            report,
            bundle_verified=True,
            verified_bytes=total,
            verified_blob_reads=report["verified_blob_reads"] + 2,
        )
    except (
        ValueError,
        OSError,
        TypeError,
        AttributeError,
        OverflowError,
        RecursionError,
        NotImplementedError,
    ):
        raise ValueError("invalid_threshold_bundle") from None


def compare(
    bundle_dir,
    split,
    *,
    expected_candidate_sha256,
    expected_manifest_sha256,
    expected_protocol_sha256,
    annotations,
    expected_annotations_sha256,
):
    """Verify the bundle, then compare frozen detectors on independently pinned truth.

    Each verification/evaluation pass retains its existing read bounds. The second
    pass rechecks hashes and retains one held-out snapshot shared by all detectors.
    """
    try:
        _require(type(split) is str and split in ("validation", "test"))
        verification = verify(
            bundle_dir,
            expected_candidate_sha256=expected_candidate_sha256,
            expected_manifest_sha256=expected_manifest_sha256,
            expected_protocol_sha256=expected_protocol_sha256,
        )
        root = os.path.normpath(bundle_dir)
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            manifest = _read_at(root_fd, "manifest.json", MAX_BYTES)
            blob_fd = os.open("blobs", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                _, model = _verify_blob(
                    blob_fd,
                    verification["artifact_sha256"],
                    candidates.MAX_CANDIDATE_BYTES,
                    retain=True,
                )
            finally:
                os.close(blob_fd)
        finally:
            os.close(root_fd)
        comparison = threshold.compare(
            model,
            manifest,
            os.path.join(root, "blobs"),
            split,
            expected_candidate_sha256=verification["artifact_sha256"],
            expected_manifest_sha256=expected_manifest_sha256,
            expected_protocol_sha256=expected_protocol_sha256,
            annotations=annotations,
            expected_annotations_sha256=expected_annotations_sha256,
        )
        return {
            "version": 1,
            "bundle_verification": verification,
            "comparison": comparison,
            "qualified": False,
        }
    except (
        ValueError,
        OSError,
        TypeError,
        AttributeError,
        OverflowError,
        RecursionError,
        NotImplementedError,
    ):
        raise ValueError("invalid_threshold_bundle") from None


def export(
    model,
    manifest,
    blob_dir,
    output_dir,
    *,
    expected_model_sha256,
    expected_manifest_sha256,
    expected_protocol_sha256,
    card,
    expected_card_sha256,
    rights,
    expected_rights_sha256,
):
    """Create a NEW bundle below a trusted parent; failures retain incomplete output.

    The model is validated but never fitted or executed. All dataset dependencies
    are copied from fresh hash-checked reads, one bounded blob at a time. Completion
    pins appear only after independent candidate verification of the destination.
    """
    try:
        _require(_filesystem_supported(write=True))
        threshold._model(
            model, expected_model_sha256, expected_manifest_sha256, expected_protocol_sha256
        )
        for payload, pin in ((card, expected_card_sha256), (rights, expected_rights_sha256)):
            _hash(pin)
            _require(type(payload) is bytes and 0 < len(payload) <= MAX_BYTES)
            _require(_digest(payload) == pin)
        descriptor = _encode(
            {
                "version": 1,
                "task": "obstacle_proposals",
                "format": "opaque",
                "artifact_sha256": expected_model_sha256,
                "preprocessing_sha256": _digest(threshold.PREPROCESSING_BYTES),
                "protocol_sha256": expected_protocol_sha256,
                "training_manifest_sha256": expected_manifest_sha256,
                "training_split": "train",
                "card_sha256": expected_card_sha256,
                "rights_sha256": expected_rights_sha256,
            }
        )
        bindings = {
            "expected_candidate_sha256": _digest(descriptor),
            "expected_manifest_sha256": expected_manifest_sha256,
            "expected_protocol_sha256": expected_protocol_sha256,
        }
        candidates.validate(descriptor, manifest, **bindings)
        doc = _parse(manifest)
        references = {doc["protocol_sha256"]}
        references.update(
            row[key] for row in doc["provenance"] for key in ("card_sha256", "rights_sha256")
        )
        references.update(
            row[key] for row in doc["samples"] for key in ("source_sha256", "artifact_sha256")
        )
        payloads = {
            _digest(data): data
            for data in (
                model,
                threshold.PREPROCESSING_BYTES,
                threshold.SEARCH_BYTES,
                card,
                rights,
            )
        }
        # Reserve candidate reads even if roles overlap dataset references, as
        # candidates.verify_artifacts rereads those roles. Include search bytes too.
        total = sum(len(data) for data in payloads.values())
        _require(total <= MAX_TOTAL_BYTES)
        source_fd = os.open(
            os.path.normpath(blob_dir), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            output = os.path.normpath(output_dir)
            os.mkdir(output, 0o700)  # No reuse, overwrite, or symlink destination.
            root_fd = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.mkdir("blobs", 0o700, dir_fd=root_fd)
                target_fd = os.open(
                    "blobs", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
                )
                try:
                    for digest in sorted(references):
                        size, data = _verify_blob(
                            source_fd, digest, MAX_TOTAL_BYTES - total, retain=True
                        )
                        total += size
                        _write(target_fd, digest, data)
                    for digest, data in sorted(payloads.items()):
                        if digest not in references:
                            _write(target_fd, digest, data)
                finally:
                    os.close(target_fd)
                _write(root_fd, "manifest.json", manifest)
                _write(root_fd, "candidate.json", descriptor)
                candidates.verify_artifacts(
                    _read_document(os.path.join(output, "candidate.json")),
                    _read_document(os.path.join(output, "manifest.json")),
                    os.path.join(output, "blobs"),
                    **bindings,
                )
                # Candidate v1 is opaque: explicitly check the additional search
                # specification which its generic verifier does not traverse.
                target_fd = os.open(
                    "blobs", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
                )
                try:
                    _verify_blob(target_fd, _digest(threshold.SEARCH_BYTES), MAX_BYTES)
                finally:
                    os.close(target_fd)
                pins = _completion_pins(
                    _digest(descriptor),
                    expected_model_sha256,
                    expected_manifest_sha256,
                    expected_protocol_sha256,
                )
                _write(root_fd, ".pins.pending", _encode(pins))
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
        finally:
            os.close(source_fd)
        return pins
    except (
        ValueError,
        OSError,
        TypeError,
        AttributeError,
        OverflowError,
        RecursionError,
        NotImplementedError,
    ):
        raise ValueError("invalid_threshold_bundle") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model")
    for name in (
        "manifest",
        "blob-dir",
        "output-dir",
        "card",
        "rights",
        "model-sha256",
        "manifest-sha256",
        "protocol-sha256",
        "card-sha256",
        "rights-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    try:
        pins = export(
            _read_document(args.model),
            _read_document(args.manifest),
            args.blob_dir,
            args.output_dir,
            expected_model_sha256=args.model_sha256,
            expected_manifest_sha256=args.manifest_sha256,
            expected_protocol_sha256=args.protocol_sha256,
            card=_read_document(args.card),
            expected_card_sha256=args.card_sha256,
            rights=_read_document(args.rights),
            expected_rights_sha256=args.rights_sha256,
        )
    except (ValueError, OSError, AttributeError, NotImplementedError):
        print("invalid_threshold_bundle", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(_encode(pins))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
