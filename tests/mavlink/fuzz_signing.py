"""60s signed-wire campaign against the installed edge wheel; synthetic keys only."""

import hashlib
import json
import random
import time
from pathlib import Path

from test_signing import SigningTests


def run():
    case = SigningTests()
    case.setUp()
    rng = random.Random(16033)
    packet = case.packet(timestamp=15_000_000)
    count = 0
    start = time.monotonic()
    try:
        while time.monotonic() - start < 60:
            if count % 2:
                damaged = bytearray(packet)
                damaged[rng.randrange(len(damaged))] ^= rng.randrange(1, 256)
                wire = bytes(damaged)
            else:
                wire = rng.randbytes(rng.randrange(400))
            case.source.ingest(wire)
            if case.source.snapshot().state != "UNKNOWN":
                raise AssertionError("unexpected_acceptance")
            count += 1
        case.source.ingest(case.packet())
        if not case.source.snapshot().samples[0].authenticated:
            raise AssertionError("valid_signature_rejected_after_campaign")
        from aethron_edge.telemetry import mavlink, signing

        return {
            "seed": 16033,
            "cases": count,
            "elapsed_s": time.monotonic() - start,
            "unexpected_acceptances": 0,
            "valid_packet_after_campaign": True,
            "installed_module_sha256": {
                module.__name__: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                for module in (mavlink, signing)
            },
        }
    finally:
        case.doCleanups()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
