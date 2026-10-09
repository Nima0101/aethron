"""Finite aggregate-only loopback diagnostic. SPDX-License-Identifier: GPL-3.0-only."""

import argparse
import json
import sys
import time

from .datagram_v1 import DatagramTelemetryV1, UdpTelemetryV1
from .mavlink import PassiveTelemetry


def _emit_status(status):
    print(
        json.dumps(
            {
                "version": 1,
                "event": "status",
                "state": status.state,
                "reason": status.reason,
                "sample_count": len(status.samples),
                "authenticated": False,
                "evidence": "external_unverified",
                "perception_eligible": False,
            },
            sort_keys=True,
        ),
        flush=True,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--duration-ms", type=int, required=True)
    parser.add_argument("--system-id", type=int, default=1)
    parser.add_argument("--component-id", type=int, default=1)
    args = parser.parse_args(argv)
    if not (
        0 <= args.port <= 65535
        and 1 <= args.duration_ms <= 30_000
        and 1 <= args.system_id <= 255
        and 1 <= args.component_id <= 255
    ):
        parser.error("invalid_diagnostic_limits")

    source = None
    try:
        source = DatagramTelemetryV1(PassiveTelemetry(args.system_id, args.component_id))
        with UdpTelemetryV1(source, port=args.port) as receiver:
            deadline = time.monotonic_ns() + args.duration_ms * 1_000_000
            print(
                json.dumps({"version": 1, "event": "listening", "port": receiver.port}),
                flush=True,
            )
            # Independent resource bound under a flood or a faulty host clock.
            for _ in range(1500):
                if time.monotonic_ns() >= deadline:
                    break
                status = receiver.poll()
                if time.monotonic_ns() >= deadline:
                    break
                _emit_status(status)
        _emit_status(source.snapshot())
        return 0
    except KeyboardInterrupt:
        return 130
    except (ImportError, OSError, RuntimeError, ValueError):
        print("telemetry_diagnostic_failed", file=sys.stderr)
        return 2
    finally:
        if source is not None:
            source.close()


if __name__ == "__main__":
    raise SystemExit(main())
