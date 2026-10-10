"""Executable managed-runtime parity experiment, with synthetic wire only."""

import asyncio
import hashlib
import importlib.util
import json

# Fixed local Python fixtures; no shell or external input.
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class LifecycleAuditTests(unittest.TestCase):
    def assert_source_receipt(self, report):
        root = Path(__file__).resolve().parents[2]
        paths = [
            "scripts/robotics_lifecycle_audit_v2.py",
            "integrations/edge/aethron_edge/telemetry/mavlink.py",
            "tests/mavlink/audit_v2/managed.mjs",
        ]
        expected = {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths}
        with self.subTest(field="source_sha256"):
            self.assertEqual(report.get("source_sha256"), expected)
        with self.subTest(field="audit_policy_version"):
            self.assertEqual(report.get("audit_policy_version"), 3)

    def setUp(self):
        path = Path(__file__).resolve().parents[2] / "scripts/robotics_lifecycle_audit_v2.py"
        self.assertTrue(path.is_file(), "missing managed lifecycle comparison")
        spec = importlib.util.spec_from_file_location("lifecycle_audit", path)
        self.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)

    def test_managed_candidate_matches_state_values_and_provenance(self):
        cases = self.api.corpus()
        self.assertGreaterEqual(len(cases), 8)
        result = self.api.compare(cases)
        self.assertTrue(result["parity"])
        self.assertGreater(result["steps"], 30)

    def test_close_expiry_and_clock_latches_have_independent_expectations(self):
        results = dict(
            zip((c["name"] for c in self.api.corpus()), self.api.reference(self.api.corpus()))
        )
        self.assertEqual(results["expiry"][-1]["reason"], "receive_expired")
        self.assertEqual(results["rollback"][-1]["reason"], "local_clock_invalid")
        self.assertEqual(results["boot_reset"][-1]["reason"], "source_clock_reset")
        self.assertEqual(results["closed"][-1]["reason"], "closed")

    def test_operation_records_reject_unknown_or_ignored_fields(self):
        for step in (
            {"op": "snapsho", "now": "0"},
            {"op": False, "now": "0"},
            {"op": "snapshot", "now": "0", "ignored": True},
            {"op": "close", "now": "0", "hex": ""},
            {"op": "ingest", "now": "0", "hex": "", "ignored": True},
        ):
            cases = [{"name": "malformed", "steps": [step]}]
            with self.subTest(runtime="python", step=step):
                with self.assertRaisesRegex(ValueError, "audit_operation"):
                    self.api.reference(cases)
            with self.subTest(runtime="javascript", step=step):
                with self.assertRaises(subprocess.CalledProcessError):
                    self.api._child(["node", str(self.api.DRIVER)], cases)

    def test_run_records_cancellation_without_swallowing_it(self):
        for error_type in (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            with (
                self.subTest(error=error_type.__name__),
                tempfile.TemporaryDirectory() as directory,
            ):
                out = Path(directory) / "attempt"
                failure = error_type("synthetic-private-diagnostic")
                with (
                    patch.object(self.api, "corpus", return_value=[]),
                    patch.object(self.api, "_child", side_effect=failure) as child,
                    self.assertRaises(error_type) as caught,
                ):
                    self.api.run(out)
                self.assertIs(caught.exception, failure)
                child.assert_called_once()
                report = json.loads((out / "result.json").read_text())
                self.assertEqual(report.get("failure_type"), error_type.__name__)
                self.assertEqual(report["state"], "failed")
                self.assertEqual(report["decision"], "PENDING")
                self.assertEqual(report["failed_attempt"], "python-0")
                self.assertEqual(report["runs"], [{}])
                self.assertNotIn("parity", report)
                self.assertNotIn("synthetic-private-diagnostic", (out / "result.json").read_text())
                self.assert_source_receipt(report)

    def test_child_rejects_ambiguous_or_nonfinite_json_before_parity(self):
        for payload in (
            '{"results": [1], "results": []}',
            '{"results": [{"perception_eligible": true, "perception_eligible": false}]}',
            '{"results": [], "peak_rss_kib": NaN}',
            '{"results": [], "peak_rss_kib": Infinity}',
            '{"results": [], "peak_rss_kib": 1e999}',
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.api._child(
                    [sys.executable, "-c", "import sys; print(sys.argv[1])", payload], []
                )

    def test_child_preserves_valid_authority_clock_and_fractional_types(self):
        payload = '{"results": [{"perception_eligible": false, "receive_ns": "9007199254740993", "values": [0.10000000149011612]}], "peak_rss_kib": 42}'
        value, elapsed = self.api._child(
            [sys.executable, "-c", "import sys; print(sys.argv[1])", payload], []
        )
        self.assertIs(value["results"][0]["perception_eligible"], False)
        self.assertEqual(value["results"][0]["receive_ns"], "9007199254740993")
        self.assertEqual(value["results"][0]["values"], [0.10000000149011612])
        self.assertIs(type(value["peak_rss_kib"]), int)
        self.assertGreater(elapsed, 0)

    def test_run_retains_exact_partial_timeout_output_and_failed_receipt(self):
        failure = subprocess.TimeoutExpired(
            ["synthetic-child"], 10, output=b"partial\xff\r\n", stderr=b"diagnostic\x00\r\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "attempt"
            with patch.object(self.api.subprocess, "run", side_effect=failure):
                with self.assertRaises(subprocess.TimeoutExpired):
                    self.api.run(out)
            self.assertTrue((out / "python-0-stdout.log").is_file())
            self.assertEqual((out / "python-0-stdout.log").read_bytes(), b"partial\xff\r\n")
            self.assertEqual((out / "python-0-stderr.log").read_bytes(), b"diagnostic\x00\r\n")
            report = json.loads((out / "result.json").read_text())
            self.assertEqual(report["state"], "failed")
            self.assertEqual(report["failure_type"], "TimeoutExpired")
            self.assertEqual(report["failed_attempt"], "python-0")
            self.assert_source_receipt(report)

    def test_later_failure_preserves_validated_measurements_and_partial_pair(self):
        valid = b'{"results": [], "peak_rss_kib": 42, "runtime": "fixture"}\n'
        failures = (
            subprocess.TimeoutExpired("fixture", 10, output=b"partial", stderr=b"timeout"),
            subprocess.CompletedProcess(["fixture"], 7, b"failed", b"exit"),
            subprocess.CompletedProcess(["fixture"], 0, b"not-json", b"json"),
            subprocess.CompletedProcess(
                ["fixture"],
                0,
                b'{"results": [], "peak_rss_kib": -1, "runtime": "fixture"}',
                b"metadata",
            ),
            subprocess.CompletedProcess(
                ["fixture"],
                0,
                b'{"results": [1], "peak_rss_kib": 42, "runtime": "fixture"}',
                b"parity",
            ),
        )
        for failure in failures:
            with self.subTest(failure=repr(failure)), tempfile.TemporaryDirectory() as directory:
                out = Path(directory) / "attempt"
                responses = [subprocess.CompletedProcess(["fixture"], 0, valid, b"")] * 3
                responses.append(failure)
                with (
                    patch.object(self.api, "corpus", return_value=[]),
                    patch.object(self.api.subprocess, "run", side_effect=responses),
                    patch.object(self.api.time, "monotonic_ns", side_effect=range(0, 80, 10)),
                ):
                    with self.assertRaises((subprocess.SubprocessError, ValueError)):
                        self.api.run(out)
                report = json.loads((out / "result.json").read_text())
                measurement = {"peak_rss_kib": 42, "runtime": "fixture", "whole_process_ns": 10}
                self.assertEqual(
                    report.get("runs"),
                    [
                        {"python": measurement, "javascript": measurement},
                        {"python": measurement},
                    ],
                )
                self.assertEqual(report["state"], "failed")
                self.assertEqual(report["decision"], "PENDING")
                self.assertEqual(report["failed_attempt"], "javascript-1")
                self.assertNotIn("parity", report)
                self.assertEqual((out / "python-1-stdout.log").read_bytes(), valid)
                self.assertEqual((out / "javascript-1-stderr.log").read_bytes(), failure.stderr)

    def test_run_retains_nonzero_exit_and_rejected_json_before_propagating(self):
        real_run = subprocess.run
        for code, output, error in (
            (7, b'{"results": []}\r\n', subprocess.CalledProcessError),
            (0, b'{"results": [1], "results": []}\r\n', ValueError),
        ):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                out = Path(directory) / "attempt"
                program = (
                    "import os,sys; "
                    f"os.write(1, {output!r}); os.write(2, b'diagnostic\\r\\n'); "
                    f"sys.exit({code})"
                )

                def controlled_child(_command, program=program, **kwargs):
                    return real_run([sys.executable, "-c", program], **kwargs)

                with patch.object(self.api.subprocess, "run", side_effect=controlled_child):
                    with self.assertRaises(error):
                        self.api.run(out)
                self.assertTrue((out / "python-0-stdout.log").is_file())
                self.assertEqual((out / "python-0-stdout.log").read_bytes(), output)
                self.assertEqual((out / "python-0-stderr.log").read_bytes(), b"diagnostic\r\n")
                report = json.loads((out / "result.json").read_text())
                self.assertEqual(report["state"], "failed")
                self.assertEqual(report["failure_type"], error.__name__)
                self.assertEqual(report["failed_attempt"], "python-0")

    def test_run_rejects_invalid_measurement_metadata_for_each_runtime(self):
        cases = self.api.corpus()[:1]
        expected = self.api.reference(cases)
        valid = {"results": expected, "peak_rss_kib": 42, "runtime": "fixture-version"}
        invalids = [dict(valid, peak_rss_kib=v) for v in (True, -1, 1.5, "42", None)]
        invalids += [
            {k: v for k, v in valid.items() if k != "peak_rss_kib"},
            {k: v for k, v in valid.items() if k != "runtime"},
            dict(valid, runtime=False),
            dict(valid, runtime=""),
            dict(valid, extra=0),
        ]
        for runtime in ("python", "javascript"):
            for invalid in invalids:

                def child(command, cases, *, label, invalid=invalid, runtime=runtime, **kwargs):
                    value = invalid if label == runtime + "-0" else valid
                    return json.loads(json.dumps(value)), 1

                with (
                    self.subTest(runtime=runtime, invalid=invalid),
                    tempfile.TemporaryDirectory() as directory,
                ):
                    out = Path(directory) / "attempt"
                    with patch.object(self.api, "corpus", return_value=cases):
                        with patch.object(self.api, "_child", side_effect=child):
                            with self.assertRaisesRegex(ValueError, "candidate_measurement_failed"):
                                self.api.run(out)
                    report = json.loads((out / "result.json").read_text())
                    self.assertEqual(report["state"], "failed")
                    self.assertEqual(report["failed_attempt"], runtime + "-0")

    def test_successful_receipt_binds_reference_and_driver_sources(self):
        cases = self.api.corpus()[:1]
        expected = self.api.reference(cases)

        def child(*args, **kwargs):
            return {"results": expected, "peak_rss_kib": 0, "runtime": "fixture-version"}, 1

        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "attempt"
            with patch.object(self.api, "corpus", return_value=cases):
                with patch.object(self.api, "_child", side_effect=child):
                    report = self.api.run(out)
            self.assertEqual(report["state"], "compared")
            self.assert_source_receipt(report)
            self.assertEqual(json.loads((out / "result.json").read_text()), report)

    def test_compare_checks_metadata_and_preserves_zero_rss(self):
        cases = self.api.corpus()[:1]
        expected = self.api.reference(cases)
        valid = {"results": expected, "peak_rss_kib": 0, "runtime": "fixture-version"}
        with patch.object(self.api, "_child", return_value=(valid, 1)):
            self.assertEqual(self.api.compare(cases)["candidate_peak_rss_kib"], 0)
        with patch.object(self.api, "_child", return_value=(dict(valid, peak_rss_kib=False), 1)):
            with self.assertRaisesRegex(ValueError, "candidate_measurement_failed"):
                self.api.compare(cases)

    def test_parity_distinguishes_boolean_authority_from_numeric_zero(self):
        self.assertTrue(callable(getattr(self.api, "check_parity", None)))
        expected = [{"perception_eligible": False, "values": [1.0]}]
        self.api.check_parity(expected, [{"perception_eligible": False, "values": [1]}])
        for value in (0, None, "false"):
            with self.assertRaisesRegex(ValueError, "managed_lifecycle_parity_failed"):
                self.api.check_parity(expected, [{"perception_eligible": value, "values": [1]}])

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
                        self.api._child(["fixture"], [], out=out, label="clock")
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
                value, elapsed = self.api._child(["fixture"], [], out=out, label="clock")
            self.assertEqual(value, {"results": []})
            self.assertEqual(elapsed, 0)
            self.assertEqual((out / "clock-stdout.log").read_bytes(), completed.stdout)
            self.assertEqual((out / "clock-stderr.log").read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()
