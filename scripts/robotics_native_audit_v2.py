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
    api = lifecycle_api()
    api.validate_cases(cases)
    lines = ["const CASES: &[&[Step]] = &["]
    operations = {"ingest": 0, "snapshot": 1, "close": 2}
    validate_operation = api.validate_operation
    for case in cases:
        steps = case["steps"]
        lines.append("&[")
        for step in steps:
            op = validate_operation(step)
            now = step["now"]
            # validate_operation already checks the shared u128/boolean domain.
            timestamp = "None" if type(now) is bool else f"Some({int(now)}u128)"
            raw = step.get("hex", "")
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


def child(command, cases, out, label, *, input_bytes=None):
    completed, elapsed = retained_process(
        command,
        out,
        label,
        timeout=10,
        input_bytes=json.dumps(cases).encode("utf-8") if input_bytes is None else input_bytes,
    )
    return decode_candidate(completed.stdout), elapsed


def run(out, *, compiler="rustc", runtime_input=False):
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
        input_bytes = None
        runtime_flags = []
        reference_path = ROOT / "scripts/robotics_lifecycle_audit_v2.py"
        api = lifecycle_api()
        cases = corpus()
        if runtime_input:
            reference_path = ROOT / "scripts/robotics_runtime_input_v3.py"
            spec = importlib.util.spec_from_file_location("runtime_input", reference_path)
            codec = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(codec)
            input_bytes = codec.encode(cases)
            (out / "runtime-input.bin").write_bytes(input_bytes)
            runtime_flags = ["--cfg", "runtime_input"]
            shutil.copyfile(DRIVER.with_name("runtime_input_v3.rs"), out / "runtime_input_v3.rs")
            report.update(
                report_schema_version=3,
                input_format="aethron-audit-v3",
                input_sha256=hashlib.sha256(input_bytes).hexdigest(),
            )
            for path in (
                "scripts/robotics_runtime_input_v3.py",
                "tests/mavlink/audit_v2/runtime_input_v3.rs",
            ):
                report["source_sha256"][path] = hashlib.sha256(
                    (ROOT / path).read_bytes()
                ).hexdigest()
        fixture = fixture_source(cases)
        (out / "native-fixture.rs").write_text(fixture)
        shutil.copyfile(DRIVER, out / "native.rs")
        report["fixture_sha256"] = hashlib.sha256(fixture.encode()).hexdigest()
        report["corpus_sha256"] = hashlib.sha256(json.dumps(cases).encode()).hexdigest()
        version, _ = retained_process(
            [compiler, "--version", "--verbose"], out, "compiler-version", timeout=10
        )
        report["compiler"] = version.stdout.decode("utf-8").strip()
        if runtime_input:
            test_binary = out.resolve() / "runtime-input-tests"
            retained_process(
                [
                    compiler,
                    "--edition=2021",
                    "-Dwarnings",
                    *runtime_flags,
                    "--test",
                    str(out / "native.rs"),
                    "-o",
                    str(test_binary),
                ],
                out,
                "runtime-input-test-compiler",
                timeout=30,
            )
            retained_process([str(test_binary)], out, "runtime-input-tests", timeout=10)
            report["runtime_input_tests_passed"] = True
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
                    *runtime_flags,
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
                            str(reference_path),
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
                    options = {"input_bytes": input_bytes} if runtime_input else {}
                    result, elapsed = child(
                        command, cases, out, f"{profile}-{repeat}-{name}", **options
                    )
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
                (
                    "Both candidates consume the same bounded versioned binary input at runtime"
                    if runtime_input
                    else "Static input constants omit candidate input JSON parsing; Python consumes JSON"
                ),
                "Python includes pymavlink and corpus encoder import; native uses two layouts",
                "Finite corpus only; native clock domain u128, Python integers are unbounded",
                "Linux VmHWM versus Python getrusage RSS; shared scheduling and warm caches",
                "No signed replay, UDP, packaging, hard-real-time or physical qualification",
            ],
        )
        return report
    except BaseException as error:
        # Record interruption/cancellation without suppressing it or continuing
        # another profile. The existing finally block retains the failed receipt.
        report["failure_type"] = type(error).__name__
        raise
    finally:
        (out / "result.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--runtime-input", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.out, runtime_input=args.runtime_input), indent=2))
