"""Bounded runtime fixture contract; uses only synthetic audit input."""

import importlib.util
import json
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    return api


class RuntimeInputTests(unittest.TestCase):
    def setUp(self):
        self.api = module("robotics_runtime_input_v3")
        self.native = module("robotics_native_audit_v2")

    def test_golden_encoding_has_exact_little_endian_values(self):
        cases = [{"name": "a", "steps": [{"op": "ingest", "now": "257", "hex": "fdff"}]}]
        golden = b"AETHAUD3\x01\x00\x01\x00\x00\x01\x01\x01" + bytes(14) + b"\x02\x00\xfd\xff"
        self.assertEqual(self.api.encode(cases), golden)
        self.assertEqual(self.api.decode(golden)[0]["steps"], cases[0]["steps"])

    def test_full_corpus_and_clock_boundaries_preserve_observations(self):
        cases = self.native.corpus() + [
            {
                "name": "clock-boundaries",
                "steps": [
                    {"op": "snapshot", "now": "000"},
                    {"op": "snapshot", "now": str(2**128 - 1)},
                    {"op": "snapshot", "now": True},
                ],
            }
        ]
        decoded = self.api.decode(self.api.encode(cases))
        self.assertEqual(
            self.native.lifecycle_api().reference(cases), self.api.lifecycle.reference(decoded)
        )

    def test_rejects_every_truncation_trailing_and_oversized_input(self):
        raw = self.api.encode([{"name": "a", "steps": [{"op": "snapshot", "now": "0"}]}])
        for invalid in [raw[:i] for i in range(len(raw))] + [raw + b"\x00", bytes(65537)]:
            with self.subTest(length=len(invalid)), self.assertRaises(ValueError):
                self.api.decode(invalid)

    def test_rejects_invalid_tags_counts_and_noncanonical_fields(self):
        raw = self.api.encode([{"name": "a", "steps": [{"op": "ingest", "now": "1", "hex": "ff"}]}])
        for offset, value in (
            (0, 0),
            (8, 0),
            (8, 65),
            (10, 0),
            (10, 65),
            (12, 3),
            (13, 2),
            (13, 0),
            (12, 1),
            (12, 2),
            (30, 255),
            (31, 255),
        ):
            broken = bytearray(raw)
            broken[offset] = value
            with self.subTest(offset=offset, value=value), self.assertRaises(ValueError):
                self.api.decode(bytes(broken))

    def test_encoder_enforces_aggregate_and_existing_operation_limits(self):
        step = {"op": "ingest", "now": "0", "hex": "00" * 320}
        cases = [{"name": str(i), "steps": [step] * 64} for i in range(4)]
        with self.assertRaisesRegex(ValueError, "too_large"):
            self.api.encode(cases)
        for step in (
            {"op": "send", "now": "0"},
            {"op": "snapshot", "now": str(2**128)},
            {"op": "ingest", "now": "0", "hex": "00" * 321},
        ):
            with self.assertRaises(ValueError):
                self.api.encode([{"name": "a", "steps": [step]}])

    def test_real_python_child_consumes_binary_and_rejects_before_output(self):
        cases = self.native.corpus()
        raw = self.api.encode(cases)
        command = [
            sys.executable,
            str(ROOT / "scripts/robotics_runtime_input_v3.py"),
            "--reference",
        ]
        completed = subprocess.run(command, input=raw, capture_output=True, timeout=10, check=True)  # nosec B603
        self.assertEqual(
            json.loads(completed.stdout)["results"], self.api.lifecycle.reference(cases)
        )
        for invalid in (raw + b"x", bytes(65537), raw[:-1]):
            failed = subprocess.run(
                command, input=invalid, capture_output=True, timeout=10, check=False
            )  # nosec B603
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(failed.stdout, b"")

    def test_runtime_runner_binds_sources_and_identical_child_bytes(self):
        inputs = []

        def process(command, out, label, **kwargs):
            if "-o" in command:
                Path(command[command.index("-o") + 1]).write_bytes(b"mock binary")
            if label.endswith("-python") or label.endswith("-rust"):
                inputs.append(kwargs["input_bytes"])
                result = {
                    "results": self.api.lifecycle.reference(self.native.corpus()),
                    "peak_rss_kib": 1,
                }
                if label.endswith("-python"):
                    result["runtime"] = "3.13.0"
                return subprocess.CompletedProcess(command, 0, json.dumps(result).encode(), b""), 1
            return subprocess.CompletedProcess(command, 0, b"mock compiler", b""), 1

        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "run"
            with patch.object(self.native, "retained_process", side_effect=process) as calls:
                report = self.native.run(out, runtime_input=True)
            self.assertEqual(len(inputs), 8)
            self.assertTrue(all(value == self.api.encode(self.native.corpus()) for value in inputs))
            self.assertEqual((out / "runtime-input.bin").read_bytes(), inputs[0])
            self.assertEqual(report["input_format"], "aethron-audit-v3")
            self.assertIn("scripts/robotics_runtime_input_v3.py", report["source_sha256"])
            self.assertIn("tests/mavlink/audit_v2/runtime_input_v3.rs", report["source_sha256"])
            self.assertTrue(any("--test" in call.args[0] for call in calls.call_args_list))

    def test_runtime_missing_compiler_retains_failed_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "run"
            with self.assertRaises(FileNotFoundError):
                self.native.run(out, compiler=str(Path(directory) / "absent"), runtime_input=True)
            report = json.loads((out / "result.json").read_text())
            self.assertEqual(report["state"], "failed")
            self.assertFalse(report["native_executed"])
            self.assertEqual(report["failure_type"], "FileNotFoundError")
            self.assertTrue((out / "runtime-input.bin").is_file())
