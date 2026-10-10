"""Versioned bounded binary input for the audit experiment, not a telemetry protocol."""

import argparse
import importlib.util
import json
import platform
import resource
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "lifecycle_audit", Path(__file__).with_name("robotics_lifecycle_audit_v2.py")
)
lifecycle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lifecycle)

MAGIC = b"AETHAUD3"
CONFIGURED_MAGIC = b"AETHAUD4"
LIMIT = 65536
OPERATIONS = ("ingest", "snapshot", "close")


def encode(cases):
    lifecycle.validate_cases(cases)
    configured = any("version" in case for case in cases)
    magic = CONFIGURED_MAGIC if configured else MAGIC
    output = bytearray(magic + len(cases).to_bytes(2, "little"))
    for case in cases:
        if configured:
            output.extend(lifecycle.case_sender(case))
        output.extend(len(case["steps"]).to_bytes(2, "little"))
        for step in case["steps"]:
            operation = lifecycle.validate_operation(step)
            valid_clock = type(step["now"]) is not bool
            clock = int(step["now"]) if valid_clock else 0
            packet = bytes.fromhex(step.get("hex", ""))
            if len(output) + 20 + len(packet) > LIMIT:
                raise ValueError("audit_input_too_large")
            output.extend((OPERATIONS.index(operation), int(valid_clock)))
            output.extend(clock.to_bytes(16, "little"))
            output.extend(len(packet).to_bytes(2, "little"))
            output.extend(packet)
    return bytes(output)


def decode(raw):
    if type(raw) is not bytes or len(raw) > LIMIT:
        raise ValueError("audit_input_too_large_or_invalid")
    offset = 0

    def take(size):
        nonlocal offset
        if offset + size > len(raw):
            raise ValueError("audit_input_truncated")
        value = raw[offset : offset + size]
        offset += size
        return value

    def count():
        value = int.from_bytes(take(2), "little")
        if not 1 <= value <= 64:
            raise ValueError("audit_input_count")
        return value

    magic = take(8)
    if magic not in (MAGIC, CONFIGURED_MAGIC):
        raise ValueError("audit_input_version")
    cases = []
    for index in range(count()):
        sender = None
        if magic == CONFIGURED_MAGIC:
            system, component = take(2)
            if system == 0 or component == 0:
                raise ValueError("audit_sender_domain")
            sender = {"system": system, "component": component}
        steps = []
        for _ in range(count()):
            operation, valid_clock = take(2)
            clock = int.from_bytes(take(16), "little")
            length = int.from_bytes(take(2), "little")
            if operation > 2 or valid_clock > 1 or (not valid_clock and clock != 0):
                raise ValueError("audit_input_tag")
            if length > 320 or (operation != 0 and length != 0):
                raise ValueError("audit_input_packet")
            packet = take(length)
            step = {"op": OPERATIONS[operation], "now": str(clock) if valid_clock else False}
            if operation == 0:
                step["hex"] = packet.hex()
            steps.append(step)
        case = {"name": f"runtime-{index}", "steps": steps}
        if sender is not None:
            case.update(version=4, sender=sender)
        cases.append(case)
    if offset != len(raw):
        raise ValueError("audit_input_trailing")
    return cases


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", action="store_true", required=True)
    parser.parse_args()
    cases = decode(sys.stdin.buffer.read(LIMIT + 1))
    results = lifecycle.reference(cases)
    print(
        json.dumps(
            {
                "results": results,
                "runtime": platform.python_version(),
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
        )
    )
