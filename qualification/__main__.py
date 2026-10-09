"""Bounded stdin entry point for qualification declaration reports."""

import argparse
import json
import sys

from .evidence import MAX_BYTES, validate


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid_qualification_manifest")


def main():
    parser = _Parser(description=__doc__)
    parser.add_argument("--now-ms", type=int, required=True)
    try:
        args = parser.parse_args()
        report = validate(sys.stdin.buffer.read(MAX_BYTES + 1), now_ms=args.now_ms)
    except (ValueError, OSError):
        print("invalid_qualification_manifest", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0 if report["declaration_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
