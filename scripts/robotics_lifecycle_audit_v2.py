"""Bounded original JavaScript versus existing Python lifecycle experiment."""

import argparse
import hashlib
import json
import math
import platform
import resource

# Fixed offline experiment commands, never shell or caller-supplied code.
import subprocess  # nosec B404
import sys
import time
from dataclasses import asdict
from pathlib import Path

from aethron_edge.telemetry.mavlink import PassiveTelemetry
from pymavlink.dialects.v20 import common

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "tests/mavlink/audit_v2/managed.mjs"


def corpus():
    def packet(seq=0, boot=10, position=False, corrupt=False, first=1):
        encoder = common.MAVLink(None, srcSystem=1, srcComponent=1)
        encoder.seq = seq
        message = (
            common.MAVLink_local_position_ned_message
            if position
            else common.MAVLink_attitude_message
        )(boot, first, 2, 3, 4, 5, 6)
        data = bytearray(message.pack(encoder))
        if corrupt:
            data[-1] ^= 1
        return data.hex()

    def ingest(at=0, **kwargs):
        return {"op": "ingest", "now": str(1_000_000_000 + at), "hex": packet(**kwargs)}

    def snap(at):
        return {"op": "snapshot", "now": str(1_000_000_000 + at)}

    cases = {
        "expiry": [snap(0), ingest(), snap(100_000_000), snap(100_000_001)],
        "independent_slots": [
            ingest(),
            ingest(50_000_000, seq=1, position=True),
            snap(100_000_001),
            snap(150_000_001),
        ],
        "rollback": [ingest(), snap(-1), snap(1), ingest(2, seq=1, boot=11)],
        "boot_reset": [ingest(), ingest(1, seq=1, boot=0), ingest(2, seq=2, boot=12)],
        "closed": [ingest(), {"op": "close", "now": "1000000001"}, ingest(2, seq=1, boot=11)],
        "sequence_wrap": [
            ingest(seq=255),
            ingest(1, seq=0, boot=11),
            ingest(2, seq=0, boot=12),
            ingest(3, seq=1, boot=12),
        ],
        "bad_then_recover": [
            ingest(),
            ingest(1, seq=1, boot=11, corrupt=True),
            ingest(2, seq=1, boot=11),
            snap(100_000_003),
        ],
        "boot_wrap": [ingest(boot=2**32 - 1), ingest(1, seq=1, boot=0), snap(2)],
        "invalid_clock": [ingest(), {"op": "snapshot", "now": True}, ingest(2, seq=1, boot=11)],
        "wide_clock": [
            {"op": "ingest", "now": str(2**53 + 1), "hex": packet()},
            {"op": "snapshot", "now": str(2**53 + 100_000_001)},
            {"op": "snapshot", "now": str(2**53 + 100_000_002)},
        ],
        "nan_values": [ingest(), ingest(1, seq=1, boot=11, first=math.nan)],
        "infinite_values": [ingest(), ingest(1, seq=1, boot=11, first=math.inf)],
        "sequence_half_range": [ingest(), ingest(1, seq=128, boot=11), ingest(2, seq=1, boot=11)],
    }
    for name, data in (
        ("empty_packet", b""),
        ("oversize_packet", bytes(281)),
        ("signed_flag", bytes.fromhex(packet())[:2] + b"\x01" + bytes.fromhex(packet())[3:]),
    ):
        cases[name] = [ingest(), {"op": "ingest", "now": "1000000001", "hex": data.hex()}]
    return [{"name": name, "steps": steps} for name, steps in cases.items()]


def validate_operation(step):
    """Validate the closed experiment record without coercing clock test values."""
    if type(step) is not dict:
        raise ValueError("audit_operation_record")
    op = step.get("op")
    if type(op) is not str or op not in ("ingest", "snapshot", "close"):
        raise ValueError("audit_operation")
    fields = {"op", "now", "hex"} if op == "ingest" else {"op", "now"}
    if step.keys() != fields:
        raise ValueError("audit_operation_record")
    return op


def reference(cases):
    results = []
    for case in cases:
        current = [None]
        source = PassiveTelemetry(1, 1, clock=lambda current=current: current[0])
        steps = []
        try:
            for step in case["steps"]:
                op = validate_operation(step)
                now = int(step["now"]) if type(step["now"]) is str else step["now"]
                current[0] = now
                if op == "ingest":
                    source.ingest(bytes.fromhex(step["hex"]))
                elif op == "close":
                    source.close()
                value = asdict(source.snapshot())
                for sample in value["samples"]:
                    sample["receive_ns"] = str(sample["receive_ns"])
                steps.append(value)
        finally:
            source.close()
        results.append(steps)
    # Normalize immutable tuples to JSON arrays for the language-neutral fixture.
    return json.loads(json.dumps(results))


def _unique_members(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_member")
        result[key] = value
    return result


def _finite_number(token):
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("nonfinite_json_number")
    return value


def _retain_output(out, label, stdout, stderr):
    if out is not None:
        (out / f"{label}-stdout.log").write_bytes(stdout or b"")
        (out / f"{label}-stderr.log").write_bytes(stderr or b"")


def _child(command, cases, *, out=None, label="child"):
    begin = time.monotonic_ns()
    try:
        # Fixed trusted audit drivers, bounded input and process lifetime; no shell.
        completed = subprocess.run(  # nosec B603
            command,
            input=json.dumps(cases).encode("utf-8"),
            capture_output=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        _retain_output(out, label, exc.stdout, exc.stderr)
        raise
    try:
        elapsed = time.monotonic_ns() - begin
    finally:
        _retain_output(out, label, completed.stdout, completed.stderr)
    completed.check_returncode()
    if type(elapsed) is not int or elapsed < 0:
        raise ValueError("invalid_process_duration")
    value = json.loads(
        completed.stdout,
        object_pairs_hook=_unique_members,
        parse_constant=_finite_number,
        parse_float=_finite_number,
    )
    return value, elapsed


def check_parity(expected, actual):
    # Python considers False == 0. Do not let that hide an authority-schema
    # mismatch; JSON numbers may differ in integer/float representation only.
    if type(expected) in (int, float):
        valid = type(actual) in (int, float) and math.isfinite(actual) and expected == actual
    elif type(expected) is not type(actual):
        valid = False
    elif type(expected) is dict:
        valid = expected.keys() == actual.keys()
        if valid:
            for key in expected:
                check_parity(expected[key], actual[key])
    elif type(expected) is list:
        valid = len(expected) == len(actual)
        if valid:
            for left, right in zip(expected, actual):
                check_parity(left, right)
    else:
        valid = expected == actual
    if not valid:
        raise ValueError("managed_lifecycle_parity_failed")


def check_measurement(value, *, runtime=True):
    """Check the declared report envelope, not measurement authenticity."""
    keys = {"results", "peak_rss_kib"}
    if runtime:
        keys.add("runtime")
    if type(value) is not dict or value.keys() != keys:
        raise ValueError("candidate_measurement_failed")
    if type(value["peak_rss_kib"]) is not int or value["peak_rss_kib"] < 0:
        raise ValueError("candidate_measurement_failed")
    if runtime and (type(value["runtime"]) is not str or not value["runtime"]):
        raise ValueError("candidate_measurement_failed")


def compare(cases):
    expected = reference(cases)
    actual, elapsed = _child(["node", str(DRIVER)], cases)
    check_measurement(actual)
    check_parity(expected, actual["results"])
    return {
        "parity": True,
        "steps": sum(len(c["steps"]) for c in cases),
        "candidate_process_ns": elapsed,
        "candidate_peak_rss_kib": actual["peak_rss_kib"],
    }


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    report = {"audit_policy_version": 3, "state": "failed", "decision": "PENDING", "runs": []}
    try:
        # Scoped repository sources, not an authenticated dependency attestation.
        report["source_sha256"] = {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "scripts/robotics_lifecycle_audit_v2.py",
                "integrations/edge/aethron_edge/telemetry/mavlink.py",
                "tests/mavlink/audit_v2/managed.mjs",
            )
        }
        cases = corpus()
        expected = reference(cases)
        (out / "expected.json").write_text(json.dumps(expected) + "\n")
        for repetition in range(3):
            pair = {}
            # Keep completed measurements even if the other runtime or a later
            # repetition fails. Only validated results enter this partial pair.
            report["runs"].append(pair)
            for name, command in (
                ("python", [sys.executable, str(Path(__file__)), "--reference"]),
                ("javascript", ["node", str(DRIVER)]),
            ):
                attempt = f"{name}-{repetition}"
                report["failed_attempt"] = attempt
                result, elapsed = _child(command, cases, out=out, label=attempt)
                check_measurement(result)
                check_parity(expected, result.pop("results"))
                pair[name] = {**result, "whole_process_ns": elapsed}
        report.pop("failed_attempt", None)
        report.update(
            state="compared",
            parity=True,
            cases=len(cases),
            steps=sum(len(c["steps"]) for c in cases),
            driver_sha256=hashlib.sha256(DRIVER.read_bytes()).hexdigest(),
            harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            fixture_sha256=hashlib.sha256(json.dumps(cases).encode()).hexdigest(),
            limitations=[
                "Whole-process time includes startup, corpus and child JSON output",
                "Parent JSON parsing and evidence writes excluded; older timings included parsing",
                "Three sequential repetitions; warm filesystem cache possible",
                "Original JS subset, not node-mavlink or NextGen SDK qualification",
                "No signed replay, UDP, installed packaging or real-time proof",
            ],
        )
        return report
    except BaseException as exc:
        # Retain the failure category for interruption/cancellation too, then
        # propagate the original object; never turn cancellation into a result.
        report["failure_type"] = type(exc).__name__
        raise
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.reference:
        # Reject the sentinel byte before parsing; text reads count characters
        # and can hide an oversized tail after an otherwise valid JSON document.
        payload = sys.stdin.buffer.read(65537)
        if len(payload) > 65536:
            raise ValueError("audit_input_too_large")
        cases = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_members,
            parse_constant=_finite_number,
            parse_float=_finite_number,
        )
        results = reference(cases)
        print(
            json.dumps(
                {
                    "results": results,
                    "runtime": platform.python_version(),
                    "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                }
            )
        )
    elif args.out is not None:
        print(json.dumps(run(args.out), indent=2))
    else:
        parser.error("supply --out")
