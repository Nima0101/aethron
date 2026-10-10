"""Executable managed-runtime parity experiment, with synthetic wire only."""

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

    def test_parity_distinguishes_boolean_authority_from_numeric_zero(self):
        self.assertTrue(callable(getattr(self.api, "check_parity", None)))
        expected = [{"perception_eligible": False, "values": [1.0]}]
        self.api.check_parity(expected, [{"perception_eligible": False, "values": [1]}])
        for value in (0, None, "false"):
            with self.assertRaisesRegex(ValueError, "managed_lifecycle_parity_failed"):
                self.api.check_parity(expected, [{"perception_eligible": value, "values": [1]}])


if __name__ == "__main__":
    unittest.main()
