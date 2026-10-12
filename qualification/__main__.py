"""Bounded stdin entry point for qualification declaration reports."""

import argparse
import json
import sys

from ._process_exit import failure, finish
from .evidence import MAX_BYTES, validate


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid_qualification_manifest")


class _Once(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error("duplicate_evaluation_instant")
        setattr(namespace, self.dest, values)


def _read_manifest(stream):
    data = bytearray()
    while len(data) <= MAX_BYTES:
        remaining = MAX_BYTES + 1 - len(data)
        chunk = stream.read(remaining)
        if type(chunk) is not bytes or len(chunk) > remaining:
            raise ValueError("invalid_qualification_manifest")
        if not chunk:
            return bytes(data)
        data.extend(chunk)
    raise ValueError("invalid_qualification_manifest")


def main():
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--now-ms", type=int, required=True, action=_Once)
    try:
        args = parser.parse_args()
        source = getattr(sys.stdin, "buffer", None)
        if source is None:
            raise ValueError("invalid_qualification_manifest")
        report = validate(_read_manifest(source), now_ms=args.now_ms)
        if sys.stdout is None:
            raise ValueError("invalid_qualification_manifest")
        print(
            json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True
        )
    except (ValueError, OSError):
        return failure("invalid_qualification_manifest")
    return 0 if report["declaration_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(finish(main()))
