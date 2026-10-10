"""Native experiment ingress and negative evidence tests; no compiler download."""

import hashlib
import importlib.util
import json

# Fixed local fixture argv and mocked process results; no shell or external code.
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class NativeAuditTests(unittest.TestCase):
    def assert_source_receipt(self, report):
        root = Path(__file__).resolve().parents[2]
        paths = [
            "scripts/robotics_native_audit_v2.py",
            "integrations/edge/aethron_edge/telemetry/mavlink.py",
            "tests/mavlink/audit_v2/native.rs",
            "scripts/robotics_lifecycle_audit_v2.py",
            "scripts/robotics_wire_audit_v2.py",
        ]
        expected = {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}
        with self.subTest(field="source_sha256"):
            self.assertEqual(report.get("source_sha256"), expected)
        with self.subTest(field="audit_policy_version"):
            self.assertEqual(report.get("audit_policy_version"), 3)

    def setUp(self):
        path = Path(__file__).resolve().parents[2] / "scripts/robotics_native_audit_v2.py"
        self.assertTrue(path.is_file(), "missing native lifecycle experiment")
        spec = importlib.util.spec_from_file_location("native_audit", path)
        self.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)

    def test_fixture_preserves_bytes_and_large_integer_clocks(self):
        fixture = self.api.fixture_source(
            [{"steps": [{"op": "ingest", "now": str(2**53 + 1), "hex": "fd00ff"}]}]
        )
        self.assertIn("Some(9007199254740993u128)", fixture)
        self.assertIn("packet: &[253,0,255]", fixture)
        self.assertNotIn("OBSERVED", fixture)  # Inputs only, no oracle outcomes.

    def test_fixture_rejects_out_of_domain_and_source_injection(self):
        for now in ("0); panic!(); (0", str(2**128), "-1", 0):
            with self.subTest(now=now), self.assertRaises(ValueError):
                self.api.fixture_source([{"steps": [{"op": "snapshot", "now": now}]}])
        for step in ({"op": "send", "now": "0"}, {"op": "ingest", "now": "0", "hex": "zz"}):
            with self.assertRaises(ValueError):
                self.api.fixture_source([{"steps": [step]}])
        for cases in ([{"steps": []}] * 65, [{"steps": [{"op": "snapshot", "now": "0"}] * 65}]):
            with self.assertRaises(ValueError):
                self.api.fixture_source(cases)

    def test_combined_corpus_checks_fractional_values_and_trimmed_payloads(self):
        cases = self.api.corpus()
        self.api.fixture_source(cases)
        expected = self.api.lifecycle_api().reference(cases)
        outputs = dict(zip((case["name"] for case in cases), expected))
        fractional = outputs["wire_attitude"][0]["samples"][0]["values"][0]
        self.assertEqual(fractional, 0.10000000149011612)
        self.assertEqual(outputs["wire_trimmed"][0]["samples"][0]["values"], [0.0] * 6)
        self.assertEqual(outputs["wire_oversize"][0]["reason"], "invalid_packet")

    def test_failed_child_retains_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with self.assertRaises(subprocess.CalledProcessError):
                self.api.child(
                    [sys.executable, "-c", "import sys; print('negative evidence'); sys.exit(3)"],
                    [],
                    out,
                    "negative",
                )
            self.assertEqual((out / "negative-stdout.log").read_text(), "negative evidence\n")

    def test_timeout_keeps_exact_partial_bytes_and_remains_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            failure = subprocess.TimeoutExpired(
                "fixed-audit-child", 10, output=b"partial\xff\r\n", stderr=b"diagnostic\x00"
            )
            with patch.object(self.api.subprocess, "run", side_effect=failure):
                with self.assertRaises(subprocess.TimeoutExpired) as caught:
                    self.api.child([sys.executable], [], out, "timeout")
            self.assertIs(caught.exception, failure)
            self.assertEqual((out / "timeout-stdout.log").read_bytes(), failure.stdout)
            self.assertEqual((out / "timeout-stderr.log").read_bytes(), failure.stderr)

    def test_failed_compiler_probe_keeps_stderr_and_failure_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "attempt"
            compiler = Path(directory) / "failing-compiler"
            compiler.write_text("#!/bin/sh\nprintf 'rejected probe\\n' >&2\nexit 3\n")
            compiler.chmod(0o700)
            with self.assertRaises(subprocess.CalledProcessError):
                self.api.run(out, compiler=str(compiler))
            self.assertTrue((out / "compiler-version-stderr.log").read_bytes())
            report = json.loads((out / "result.json").read_text())
            self.assertEqual(report["state"], "failed")
            self.assertEqual(report["failure_type"], "CalledProcessError")
            self.assertFalse(report["native_executed"])

    def test_candidate_json_cannot_hide_duplicate_members_or_nonfinite_numbers(self):
        for label, payload, reason in (
            ("duplicate", '{"results": [], "results": [1]}', "duplicate_json_member"),
            (
                "nested",
                '{"results": [{"perception_eligible": true, "perception_eligible": false}]}',
                "duplicate_json_member",
            ),
            ("nan", '{"results": [], "peak_rss_kib": NaN}', "nonfinite_json_number"),
            ("overflow", '{"results": [], "peak_rss_kib": 1e999}', "nonfinite_json_number"),
            ("infinity", '{"results": [], "peak_rss_kib": Infinity}', "nonfinite_json_number"),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                with self.assertRaisesRegex(ValueError, reason):
                    self.api.child(
                        [sys.executable, "-c", "import sys; print(sys.argv[1])", payload],
                        [],
                        out,
                        label,
                    )
                self.assertEqual((out / f"{label}-stdout.log").read_text(), payload + "\n")

    def test_candidate_json_preserves_valid_types_and_fractional_values(self):
        value = self.api.decode_candidate(
            b'{"results": [{"perception_eligible": false, "receive_ns": "9007199254740993", "values": [0.10000000149011612]}], "peak_rss_kib": 42}'
        )
        self.assertIs(value["results"][0]["perception_eligible"], False)
        self.assertEqual(value["results"][0]["receive_ns"], "9007199254740993")
        self.assertEqual(value["results"][0]["values"], [0.10000000149011612])
        self.assertIs(type(value["peak_rss_kib"]), int)

    def test_run_validates_measurements_in_both_profiles(self):
        cases = [{"name": "empty", "steps": [{"op": "snapshot", "now": "0"}]}]
        expected = self.api.lifecycle_api().reference(cases)

        def process(command, out, label, **kwargs):
            if label.endswith("-compiler"):
                Path(command[-1]).write_bytes(b"fixture binary; never executed")
            return subprocess.CompletedProcess(
                command, 0, stdout=b"fixture compiler", stderr=b""
            ), 1

        for target in (
            "checked-0-python",
            "checked-0-rust",
            "optimized-0-python",
            "optimized-0-rust",
            None,
        ):

            def child(command, cases, out, label, target=target):
                value = {"results": expected, "peak_rss_kib": 0}
                if label.endswith("-python"):
                    value["runtime"] = "fixture-version"
                if label == target:
                    value["peak_rss_kib"] = False
                return value, 1

            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                out = Path(directory) / "attempt"
                # Exercise report admission without claiming native compilation/execution.
                with patch.object(self.api, "corpus", return_value=cases):
                    with patch.object(self.api, "retained_process", side_effect=process):
                        with patch.object(self.api, "child", side_effect=child):
                            if target is None:
                                report = self.api.run(out)
                                self.assertEqual(report["state"], "compared")
                                self.assert_source_receipt(report)
                                self.assertEqual(len(report["runs"]), 4)
                                self.assertEqual(report["runs"][-1]["rust"]["peak_rss_kib"], 0)
                            else:
                                with self.assertRaisesRegex(
                                    ValueError, "candidate_measurement_failed"
                                ):
                                    self.api.run(out)
                report = json.loads((out / "result.json").read_text())
                if target is not None:
                    self.assertEqual(report["state"], "failed")
                    self.assertEqual(report["failure_type"], "ValueError")

    def test_missing_compiler_is_failure_with_retained_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "attempt"
            missing = str(Path(directory) / "absent-rustc")
            with self.assertRaises(FileNotFoundError):
                self.api.run(out, compiler=missing)
            result = json.loads((out / "result.json").read_text())
            self.assertEqual(result["state"], "failed")
            self.assertFalse(result["native_executed"])
            self.assertEqual(result["decision"], "PENDING")
            self.assert_source_receipt(result)
            original = (out / "result.json").read_bytes()
            with self.assertRaises(FileExistsError):
                self.api.run(out, compiler=missing)
            self.assertEqual((out / "result.json").read_bytes(), original)

    def test_finishing_clock_failure_retains_bytes_and_rejects_duration(self):
        completed = subprocess.CompletedProcess(
            ["fixture"], 0, b'{"results": []}\r\n', b"diagnostic\x00\r\n"
        )
        for ending in (RuntimeError("synthetic_clock_failure"), -1, 0.5):
            error = RuntimeError if isinstance(ending, Exception) else ValueError
            reason = (
                "synthetic_clock_failure" if error is RuntimeError else "invalid_process_duration"
            )
            with self.subTest(ending=ending), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                with (
                    patch.object(self.api.subprocess, "run", return_value=completed),
                    patch.object(self.api.time, "monotonic_ns", side_effect=[0, ending]),
                ):
                    with self.assertRaisesRegex(error, reason):
                        self.api.child(["fixture"], [], out, "clock")
                self.assertTrue((out / "clock-stdout.log").is_file(), "missing captured output")
                self.assertEqual((out / "clock-stdout.log").read_bytes(), completed.stdout)
                self.assertEqual((out / "clock-stderr.log").read_bytes(), completed.stderr)

    def test_zero_process_duration_preserves_output(self):
        completed = subprocess.CompletedProcess(["fixture"], 0, b'{"results": []}', b"")
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with (
                patch.object(self.api.subprocess, "run", return_value=completed),
                patch.object(self.api.time, "monotonic_ns", return_value=0),
            ):
                value, elapsed = self.api.child(["fixture"], [], out, "clock")
            self.assertEqual(value, {"results": []})
            self.assertEqual(elapsed, 0)
            self.assertEqual((out / "clock-stdout.log").read_bytes(), completed.stdout)
            self.assertEqual((out / "clock-stderr.log").read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()
