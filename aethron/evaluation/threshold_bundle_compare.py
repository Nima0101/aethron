"""Compare an experimental offline bundle on independently pinned held-out labels."""

import argparse
import sys

from .splits import _read_document
from .threshold import _encode
from .threshold_bundle import compare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle")
    for name in (
        "split",
        "candidate-sha256",
        "manifest-sha256",
        "protocol-sha256",
        "annotations",
        "annotations-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    try:
        report = compare(
            args.bundle,
            args.split,
            expected_candidate_sha256=args.candidate_sha256,
            expected_manifest_sha256=args.manifest_sha256,
            expected_protocol_sha256=args.protocol_sha256,
            annotations=_read_document(args.annotations),
            expected_annotations_sha256=args.annotations_sha256,
        )
    except (ValueError, OSError, AttributeError, NotImplementedError):
        print("invalid_threshold_bundle", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(_encode(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
