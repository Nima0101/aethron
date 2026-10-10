"""Read one bounded v1 binary frame and emit a non-qualifying bundle report."""

import json
import struct
import sys

from ._process_exit import finish
from .campaign import MAX_CAPTURES
from .campaign_bundle import evaluate
from .campaign_references import MAX_REFERENCE_BYTES
from .evidence import MAX_BYTES, _integer, _token

MAGIC = b"AETHRON-QUALIFICATION-BUNDLE-V1\n"


def _read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if type(chunk) is not bytes or not chunk or len(chunk) > size - len(data):
            raise ValueError("invalid_campaign_bundle")
        data.extend(chunk)
    return bytes(data)


def _length(stream, maximum):
    size = struct.unpack(">I", _read_exact(stream, 4))[0]
    if size > maximum:
        raise ValueError("invalid_campaign_bundle")
    return size


def _blob(stream, maximum):
    return _read_exact(stream, _length(stream, maximum))


def _report(stream):
    if _read_exact(stream, len(MAGIC)) != MAGIC:
        raise ValueError("invalid_campaign_bundle")
    plan = _blob(stream, MAX_BYTES)
    domain = _blob(stream, MAX_REFERENCE_BYTES)
    procedure = _blob(stream, MAX_REFERENCE_BYTES)
    rows = []
    for _ in range(_length(stream, MAX_CAPTURES)):
        case_id = _blob(stream, 64).decode("ascii")
        _token(case_id)
        now_ms = struct.unpack(">Q", _read_exact(stream, 8))[0]
        _integer(now_ms)
        rows.append({"case_id": case_id, "now_ms": now_ms, "manifest": _blob(stream, MAX_BYTES)})
    if stream.read(1) != b"":
        raise ValueError("invalid_campaign_bundle")
    return evaluate(plan, rows, domain, procedure)


def main():
    try:
        if len(sys.argv) != 1:
            raise ValueError("invalid_campaign_bundle")
        report = _report(sys.stdin.buffer)
        print(
            json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True
        )
    except (ValueError, OSError):
        print("invalid_campaign_bundle", file=sys.stderr)
        return 2
    return 0 if report["software_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(finish(main()))
