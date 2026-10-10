"""Bounded Rust lifecycle experiment; compilation uses an existing local compiler."""

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import shutil

# Fixed local compiler and candidate commands; no shell, downloads or remote input.
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "tests/mavlink/audit_v2/native.rs"


def lifecycle_api():
    spec = importlib.util.spec_from_file_location(
        "lifecycle_audit", ROOT / "scripts/robotics_lifecycle_audit_v2.py"
    )
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    return api


def corpus():
    api = lifecycle_api()
    spec = importlib.util.spec_from_file_location(
        "wire_audit", ROOT / "scripts/robotics_wire_audit_v2.py"
    )
    wire = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wire)
    return api.corpus() + [
        {
            "name": "wire_" + case["name"],
            "steps": [{"op": "ingest", "now": "1000000000", "hex": case["hex"]}],
        }
        for case in wire.corpus()
    ]


def fixture_source(cases):
    """Emit only validated input constants, never candidate results or raw strings."""
    if type(cases) is not list or not 1 <= len(cases) <= 64:
        raise ValueError("audit_case_limit")
    lines = ["const CASES: &[&[Step]] = &["]
    operations = {"ingest": 0, "snapshot": 1, "close": 2}
    for case in cases:
        steps = case["steps"]
        if type(steps) is not list or not 1 <= len(steps) <= 64:
            raise ValueError("audit_step_limit")
        lines.append("&[")
        for step in steps:
            now = step["now"]
            if type(now) is bool:  # Preserve the invalid-clock test, not numeric 0/1.
                timestamp = "None"
            elif type(now) is str and now.isascii() and now.isdecimal() and len(now) <= 39:
                value = int(now)
                if value >= 2**128:
                    raise ValueError("audit_clock_domain")
                timestamp = f"Some({value}u128)"
            else:
                raise ValueError("audit_clock_domain")
            op = step["op"]
            if op not in operations:
                raise ValueError("audit_operation")
            raw = step.get("hex", "")
            if type(raw) is not str or len(raw) > 640:
                raise ValueError("audit_packet_limit")
            packet = bytes.fromhex(raw)
            values = ",".join(str(value) for value in packet)
            lines.append(f"Step {{ op: {operations[op]}, now: {timestamp}, packet: &[{values}] }},")
        lines.append("],")
    lines.append("];")
    return "\n".join(lines) + "\n"


def retained_process(command, out, label, *, timeout, input_bytes=None):
    """Keep exact diagnostic bytes on both normal exit and subprocess timeout."""
    begin = time.monotonic_ns()
    try:
        completed = subprocess.run(  # nosec B603
            command, input=input_bytes, capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as error:
        # TimeoutExpired can carry bytes even in text mode. Keep them losslessly.
        (out / f"{label}-stdout.log").write_bytes(error.stdout or b"")
        (out / f"{label}-stderr.log").write_bytes(error.stderr or b"")
        raise
    try:
        elapsed = time.monotonic_ns() - begin
    finally:
        (out / f"{label}-stdout.log").write_bytes(completed.stdout)
        (out / f"{label}-stderr.log").write_bytes(completed.stderr)
    completed.check_returncode()
    if type(elapsed) is not int or elapsed < 0:
        raise ValueError("invalid_process_duration")
    return completed, elapsed


def unique_members(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_member")
        result[key] = value
    return result


def finite_number(token):
    value = float(token)
    if not math.isfinite(value):
        raise ValueError("nonfinite_json_number")
    return value


def decode_candidate(raw):
    return json.loads(
        raw,
        object_pairs_hook=unique_members,
        parse_constant=finite_number,
        parse_float=finite_number,
    )


def child(command, cases, out, label):
    completed, elapsed = retained_process(
        command, out, label, timeout=10, input_bytes=json.dumps(cases).encode("utf-8")
    )
    return decode_candidate(completed.stdout), elapsed


def run(out, *, compiler="rustc"):
    out.mkdir(parents=True, exist_ok=False)
    report = {
        "audit_policy_version": 3,
        "report_schema_version": 2,
        "state": "failed",
        "decision": "PENDING",
        "native_executed": False,
        "native_attempts": 0,
        "platform": platform.platform(),
        "driver_sha256": hashlib.sha256(DRIVER.read_bytes()).hexdigest(),
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    try:
        # Scoped repository sources, not an authenticated dependency attestation.
        report["source_sha256"] = {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "scripts/robotics_native_audit_v2.py",
                "integrations/edge/aethron_edge/telemetry/mavlink.py",
                "tests/mavlink/audit_v2/native.rs",
                "scripts/robotics_lifecycle_audit_v2.py",
                "scripts/robotics_wire_audit_v2.py",
            )
        }
        api = lifecycle_api()
        cases = corpus()
        fixture = fixture_source(cases)
        (out / "native-fixture.rs").write_text(fixture)
        shutil.copyfile(DRIVER, out / "native.rs")
        report["fixture_sha256"] = hashlib.sha256(fixture.encode()).hexdigest()
        report["corpus_sha256"] = hashlib.sha256(json.dumps(cases).encode()).hexdigest()
        version, _ = retained_process(
            [compiler, "--version", "--verbose"], out, "compiler-version", timeout=10
        )
        report["compiler"] = version.stdout.decode("utf-8").strip()
        expected = api.reference(cases)
        (out / "expected.json").write_text(json.dumps(expected, indent=2) + "\n")
        report.update(cases=len(cases), steps=sum(len(c["steps"]) for c in cases), runs=[])
        for profile, flags in (
            ("checked", ["-C", "opt-level=0", "-C", "overflow-checks=yes"]),
            ("optimized", ["-C", "opt-level=2", "-C", "overflow-checks=yes"]),
        ):
            binary = out.resolve() / profile
            retained_process(
                [
                    compiler,
                    "--edition=2021",
                    "-Dwarnings",
                    *flags,
                    str(out / "native.rs"),
                    "-o",
                    str(binary),
                ],
                out,
                f"{profile}-compiler",
                timeout=30,
            )
            report[f"{profile}_binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
            for repeat in range(1 if profile == "checked" else 3):
                pair = {"profile": profile}
                report["runs"].append(pair)
                for name, command in (
                    (
                        "python",
                        [
                            sys.executable,
                            str(ROOT / "scripts/robotics_lifecycle_audit_v2.py"),
                            "--reference",
                        ],
                    ),
                    ("rust", [str(binary)]),
                ):
                    if name == "rust":
                        report["native_attempts"] += 1
                        # A failed wrapper may already have run the candidate. Unknown
                        # is not evidence of non-execution; preserve earlier confirmation.
                        if report["native_executed"] is False:
                            report["native_executed"] = None
                    result, elapsed = child(command, cases, out, f"{profile}-{repeat}-{name}")
                    if name == "rust":
                        report["native_executed"] = True
                    api.check_measurement(result, runtime=name == "python")
                    api.check_parity(expected, result.pop("results"))
                    pair[name] = {**result, "whole_process_ns": elapsed}
        report.update(
            state="compared",
            parity=True,
            limitations=[
                "Original Rust strict subset, not rust-mavlink SDK qualification",
                "Static input constants omit candidate input JSON parsing; Python consumes JSON",
                "Python includes pymavlink and corpus encoder import; native uses two layouts",
                "Finite corpus only; native clock domain u128, Python integers are unbounded",
                "Linux VmHWM versus Python getrusage RSS; shared scheduling and warm caches",
                "No signed replay, UDP, packaging, hard-real-time or physical qualification",
            ],
        )
        return report
    except Exception as error:
        report["failure_type"] = type(error).__name__
        raise
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    print(json.dumps(run(parser.parse_args().out), indent=2))
