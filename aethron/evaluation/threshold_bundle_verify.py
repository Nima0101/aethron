"""Verify an offline scalar bundle against externally supplied trusted pins."""

import argparse
import sys

from .threshold import _encode
from .threshold_bundle import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle")
    for name in ("candidate-sha256", "manifest-sha256", "protocol-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    try:
        report = verify(
            args.bundle,
            expected_candidate_sha256=args.candidate_sha256,
            expected_manifest_sha256=args.manifest_sha256,
            expected_protocol_sha256=args.protocol_sha256,
        )
    except ValueError:
        print("invalid_threshold_bundle", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(_encode(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
