"""Bounded stdin entry point for qualification declaration reports."""

import argparse
import json
import sys

from .evidence import MAX_BYTES, validate


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid_qualification_manifest")


class _Once(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error("duplicate_evaluation_instant")
        setattr(namespace, self.dest, values)


def main():
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--now-ms", type=int, required=True, action=_Once)
    try:
        args = parser.parse_args()
        report = validate(sys.stdin.buffer.read(MAX_BYTES + 1), now_ms=args.now_ms)
        print(
            json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True
        )
    except (ValueError, OSError):
        print("invalid_qualification_manifest", file=sys.stderr)
        return 2
    return 0 if report["declaration_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
