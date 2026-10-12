"""Consume one offline raw assessment: ``python -m qualification.assessment_cli``.

Frame v1: MAGIC, plan/domain/procedure blobs, method map, capture count, captures,
then EOF. A blob is a big-endian uint32 byte length followed by its exact bytes.
A map is a uint32 count followed by distinct 64-byte lowercase ASCII SHA-256 keys
and blobs. A capture is a case-ID blob, now_ms blob, manifest blob, artifact map.
The now_ms blob is an ASCII JSON integer token of at most 17 bytes, retaining
rejection of boolean/float values instead of coercing them to binary integers.
All counts/lengths use assessment v1 limits; artifact bytes sum across captures.
This is a separate protocol from campaign bundle v1. No paths or reports are read.
Exit 0 means software checks pass, 1 retains negative findings, 2 means a fixed
input/output failure. None of these statuses grants physical qualification.
"""

import json
import sys

from ._process_exit import failure, finish
from .artifacts import MAX_ARTIFACT_BYTES, MAX_ARTIFACTS, MAX_TOTAL_BYTES
from .assessment import evaluate
from .campaign import MAX_CAPTURES
from .campaign_bundle_cli import _blob, _length, _read_exact
from .evidence import MAX_BYTES, _hash, _integer, _parse_integer, _token
from .methods import MAX_METHOD_BYTES, MAX_METHODS

MAGIC = b"AETHRON-QUALIFICATION-ASSESSMENT-V1\n"


def _byte_map(stream, count, size, remaining):
    supplied = {}
    for _ in range(_length(stream, count)):
        digest = _read_exact(stream, 64).decode("ascii")
        _hash(digest)
        if digest in supplied:
            raise ValueError("invalid_qualification_assessment")
        # Check the remaining aggregate allowance before consuming the payload.
        raw = _blob(stream, min(size, remaining))
        remaining -= len(raw)
        supplied[digest] = raw
    return supplied, remaining


def _report(stream):
    if _read_exact(stream, len(MAGIC)) != MAGIC:
        raise ValueError("invalid_qualification_assessment")
    plan = _blob(stream, MAX_BYTES)
    domain = _blob(stream, MAX_BYTES)
    procedure = _blob(stream, MAX_BYTES)
    methods, _ = _byte_map(stream, MAX_METHODS, MAX_METHOD_BYTES, MAX_METHODS * MAX_METHOD_BYTES)
    captures, remaining = [], MAX_TOTAL_BYTES
    for _ in range(_length(stream, MAX_CAPTURES)):
        case_id = _blob(stream, 64).decode("ascii")
        _token(case_id)
        now_ms = json.loads(_blob(stream, 17).decode("ascii"), parse_int=_parse_integer)
        _integer(now_ms)
        manifest = _blob(stream, MAX_BYTES)
        artifacts, remaining = _byte_map(stream, MAX_ARTIFACTS, MAX_ARTIFACT_BYTES, remaining)
        captures.append(
            {"case_id": case_id, "now_ms": now_ms, "manifest": manifest, "artifacts": artifacts}
        )
    tail = stream.read(1)
    if type(tail) is not bytes or tail:
        raise ValueError("invalid_qualification_assessment")
    return evaluate(plan, captures, domain, procedure, methods)


def main():
    try:
        if len(sys.argv) != 1:
            raise ValueError("invalid_qualification_assessment")
        source = getattr(sys.stdin, "buffer", None)
        if source is None:
            raise ValueError("invalid_qualification_assessment")
        report = _report(source)
        if sys.stdout is None:
            raise ValueError("invalid_qualification_assessment")
        print(
            json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False), flush=True
        )
    except (ValueError, OSError):
        return failure("invalid_qualification_assessment")
    return 0 if report["software_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(finish(main()))
