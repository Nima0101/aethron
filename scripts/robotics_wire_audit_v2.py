"""Bounded offline technology-audit experiment; never a runtime/vehicle adapter."""

import argparse
import contextlib
import hashlib
import json
import math
import platform

# Fixed compiler/experiment argv on a trusted development host, without a shell.
import subprocess  # nosec B404
import time

# Only the trusted installed SDK's XML is read, not external/user input.
import xml.etree.ElementTree as ET  # nosec B405
from importlib.metadata import version
from pathlib import Path

from aethron_edge.telemetry.mavlink import PassiveTelemetry
from pymavlink.dialects.v20 import common

ROOT = Path(__file__).resolve().parents[1]


def corpus():
    encoder = common.MAVLink(None, srcSystem=1, srcComponent=1)
    full = common.MAVLink_attitude_message(10, 0.1, -0.2, 0.3, 0.4, -0.5, 0.6).pack(encoder)
    position = common.MAVLink_local_position_ned_message(10, 1, 2, 3, 4, 5, 6).pack(encoder)
    trimmed = common.MAVLink_attitude_message(0, 0, 0, 0, 0, 0, 0).pack(encoder)
    nan = common.MAVLink_attitude_message(10, math.nan, 0, 0, 0, 0, 0).pack(encoder)
    inf = common.MAVLink_attitude_message(10, math.inf, 0, 0, 0, 0, 0).pack(encoder)
    values = [
        ("attitude", full, True, 30),
        ("position", position, True, 32),
        ("trimmed", trimmed, True, 30),
        ("nan", nan, False, 30),
        ("infinity", inf, False, 30),
    ]
    for name, data in (
        ("empty", b""),
        ("short", full[:-1]),
        ("trailing", full + b"x"),
        ("oversize", full * 8),
        ("crc", full[:-1] + bytes([full[-1] ^ 1])),
    ):
        values.append((name, data, False, 30))
    for name, offset, value in (
        ("v1_magic", 0, 254),
        ("signed_flag", 2, 1),
        ("unknown_flag", 2, 2),
        ("compatibility_flag", 3, 1),
        ("sender", 5, 2),
        ("component", 6, 2),
        ("unsupported_message", 7, 0),
    ):
        data = bytearray(full)
        data[offset] = value
        values.append((name, bytes(data), False, 30))
    return [
        {"name": name, "hex": data.hex(), "accepted": accepted, "message": message}
        for name, data, accepted, message in values
    ]


def _result(source, packet):
    source.ingest(packet)
    status = source.snapshot()
    if not status.samples:
        return {"accepted": False}
    sample = status.samples[0]
    return {
        "accepted": True,
        "message": 30 if sample.message == "ATTITUDE" else 32,
        "boot": sample.source_boot_ms,
        "values": list(sample.values),
    }


def python_result(packet):
    source = PassiveTelemetry(1, 1, clock=lambda: 1_000_000_000)
    try:
        return _result(source, packet)
    finally:
        source.close()


def check_parity(expected, actual):
    if len(expected) != len(actual):
        raise ValueError("candidate_parity_failed")
    for left, right in zip(expected, actual):
        if left.keys() != right.keys():
            raise ValueError("candidate_parity_failed")
        for key in left:
            if key == "values":
                if len(left[key]) != len(right[key]) or not all(
                    type(y) in (int, float)
                    and math.isfinite(y)
                    and math.isclose(x, y, rel_tol=1e-8, abs_tol=1e-9)
                    for x, y in zip(left[key], right[key])
                ):
                    raise ValueError("candidate_parity_failed")
            elif type(left[key]) is not type(right[key]) or left[key] != right[key]:
                raise ValueError("candidate_parity_failed")


def check_benchmark(expected, actual):
    fields = {"samples", "accepted", "p50_ns", "p95_ns", "max_ns"}
    if type(actual) is not dict or actual.keys() != fields:
        raise ValueError("candidate_benchmark_failed")
    if not all(type(value) is int and 0 <= value < 2**64 for value in actual.values()):
        raise ValueError("candidate_benchmark_failed")
    # Match the fixed round-robin probe schedule in reference.c, not its self-report.
    accepted = sum(expected[i % len(expected)]["accepted"] for i in range(512))
    if (
        actual["samples"] != 512
        or actual["accepted"] != accepted
        or not actual["p50_ns"] <= actual["p95_ns"] <= actual["max_ns"]
    ):
        raise ValueError("candidate_benchmark_failed")


def _execute(command, *, timeout, out, label):
    # All callers supply fixed local commands; no shell or remote installer.
    try:
        completed = subprocess.run(  # nosec B603
            command, check=False, capture_output=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as error:
        (out / f"{label}-stdout.log").write_bytes(error.stdout or b"")
        (out / f"{label}-stderr.log").write_bytes(error.stderr or b"")
        raise
    (out / f"{label}-stdout.log").write_bytes(completed.stdout)
    (out / f"{label}-stderr.log").write_bytes(completed.stderr)
    completed.check_returncode()
    return completed.stdout.decode("utf-8")


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


def decode_candidate(raw):
    return json.loads(
        raw,
        object_pairs_hook=_unique_members,
        parse_constant=_finite_number,
        parse_float=_finite_number,
    )


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "audit_policy_version": 2,
        "state": "failed",
        "decision": "PENDING",
        "scope": "fresh unsigned packet admission only; not lifecycle/signing parity",
        "failed_stage": "setup",
    }

    def execute(command, label, timeout):
        report["failed_stage"] = label
        return _execute(command, timeout=timeout, out=out, label=label)

    try:
        if version("pymavlink") != "2.4.50":
            raise ValueError("unreviewed_sdk")
        xml = Path(common.__file__).with_suffix(".xml")
        # Trusted hash-recorded installed SDK data, never caller XML.
        tree = ET.parse(xml)  # nosec B314
        subset = ET.Element("mavlink")
        ET.SubElement(subset, "version").text = "3"
        messages = ET.SubElement(subset, "messages")
        for message in tree.findall("messages/message"):
            if message.attrib["id"] in {"30", "32"}:
                messages.append(message)
        if len(messages) != 2:
            raise ValueError("missing_wire_definitions")
        subset_path = out / "subset.xml"
        ET.ElementTree(subset).write(subset_path)
        from pymavlink.generator import mavgen

        report["failed_stage"] = "generation"
        with (out / "generation.log").open("w") as log, contextlib.redirect_stdout(log):
            if not mavgen.mavgen(
                mavgen.Opts(str(out / "generated"), wire_protocol="2.0", language="C"),
                [str(subset_path)],
            ):
                raise ValueError("generation_failed")
        cases = corpus()
        (out / "corpus.json").write_text(json.dumps(cases, indent=2) + "\n")
        packets = [bytes.fromhex(case["hex"]) for case in cases]
        expected = [python_result(data) for data in packets]
        (out / "expected.json").write_text(json.dumps(expected, indent=2) + "\n")
        vectors = ["static const uint8_t vectors[][320] = {"]
        vectors.extend("{" + ",".join(map(str, data or b"\0")) + "}," for data in packets)
        vectors += [
            "};",
            "static const size_t lengths[] = {"
            + ",".join(str(len(data)) for data in packets)
            + "};",
            f"#define VECTOR_COUNT {len(packets)}",
        ]
        (out / "vectors.h").write_text("\n".join(vectors) + "\n")
        driver = ROOT / "tests/mavlink/audit_v2/reference.c"
        executable = (out / "reference").resolve()
        command = [
            "cc",
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(out),
            "-isystem",
            str(out / "generated"),
            str(driver),
            "-o",
            str(executable),
        ]
        execute(command, "compiler", 30)
        candidate = decode_candidate(execute([str(executable)], "candidate", 5))
        check_parity(expected, candidate["results"])
        check_benchmark(expected, candidate.get("benchmark"))
        sanitized = (out / "reference-sanitized").resolve()
        execute(
            command[:-2]
            + ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-o", str(sanitized)],
            "sanitized-compiler",
            30,
        )
        sanitized_candidate = decode_candidate(execute([str(sanitized)], "sanitized-candidate", 5))
        check_parity(expected, sanitized_candidate["results"])
        check_benchmark(expected, sanitized_candidate.get("benchmark"))
        report["failed_stage"] = "baseline"
        for case, result in zip(cases, expected):
            if case["accepted"] != result["accepted"]:
                raise ValueError("baseline_contract_failed")
        timings, accepted = [], 0
        for index in range(512):
            source = PassiveTelemetry(1, 1, clock=lambda: 1_000_000_000)
            begin = time.monotonic_ns()
            result = _result(source, packets[index % len(packets)])
            timings.append(time.monotonic_ns() - begin)
            accepted += result["accepted"]
            source.close()
        timings.sort()
        report.update(
            state="compared",
            corpus_cases=len(cases),
            parity=True,
            sanitized_parity=True,
            python={
                "samples": 512,
                "accepted": accepted,
                "p50_ns": timings[255],
                "p95_ns": timings[486],
                "max_ns": timings[511],
            },
            c=candidate["benchmark"],
            python_version=platform.python_version(),
            machine=platform.machine(),
            system=platform.system(),
            compiler=execute(["cc", "--version"], "compiler-version", 5).splitlines()[0],
            xml_sha256=hashlib.sha256(xml.read_bytes()).hexdigest(),
            driver_sha256=hashlib.sha256(driver.read_bytes()).hexdigest(),
            harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            corpus_sha256=hashlib.sha256((out / "corpus.json").read_bytes()).hexdigest(),
            pymavlink=version("pymavlink"),
            limitations=[
                "512 mixed valid/invalid probes; no hard-real-time claim",
                "Python constructor excluded; C stack setup included",
                "C omits state, provenance objects and persistent replay",
                "No memory, cold-start, signed, UDP or SITL comparison",
            ],
        )
        report.pop("failed_stage")
        return report
    except Exception as error:
        report["failure_type"] = type(error).__name__
        raise
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    print(json.dumps(run(parser.parse_args().out), indent=2))
