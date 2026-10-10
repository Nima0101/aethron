"""Native experiment ingress and negative evidence tests; no compiler download."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class NativeAuditTests(unittest.TestCase):
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
            original = (out / "result.json").read_bytes()
            with self.assertRaises(FileExistsError):
                self.api.run(out, compiler=missing)
            self.assertEqual((out / "result.json").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
