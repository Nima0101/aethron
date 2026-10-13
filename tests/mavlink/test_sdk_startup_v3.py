"""Bounded installed-SDK startup and fallback characterization."""

import hashlib
import json

# Fixed local probe and literal modes, no shell or caller-supplied code.
import subprocess  # nosec B404
import sys
import unittest
from pathlib import Path


@unittest.skipUnless(sys.platform == "linux", "probe uses Linux RSS units and installed artifacts")
class SdkStartupTests(unittest.TestCase):
    def setUp(self):
        self.probe = Path(__file__).with_name("sdk_startup_probe_v3.py")
        self.assertTrue(self.probe.is_file(), "missing isolated SDK startup probe")

    def test_installed_and_import_failure_paths_preserve_receipt_contract(self):
        for mode, backend in (("installed", "_x25crc_fast"), ("blocked", "_x25crc_slow")):
            with self.subTest(mode=mode):
                result = subprocess.run(  # nosec B603
                    [sys.executable, "-I", str(self.probe), mode],
                    capture_output=True,
                    timeout=10,
                    check=True,
                )
                report = json.loads(result.stdout)
                self.assertEqual(report["crc_backend"], backend)
                self.assertEqual(report["mode"], mode)
                self.assertTrue(report["isolated"])
                self.assertEqual(report["initial_state"], "UNKNOWN")
                self.assertEqual(report["messages"], ["ATTITUDE", "LOCAL_POSITION_NED"])
                self.assertIn("accepted_status", report)
                accepted = report["accepted_status"]
                self.assertIn("closure_status", report)
                closure = report["closure_status"]
                self.assertEqual(report["schema_version"], 3)
                self.assertEqual(closure["before_close_state"], "OBSERVED_UNVERIFIED")
                self.assertEqual(
                    closure["before_close_messages"], ["ATTITUDE", "LOCAL_POSITION_NED"]
                )
                for stage in ("after_close", "after_readmission_attempt"):
                    status = closure[stage]
                    self.assertEqual(status["state"], "UNKNOWN")
                    self.assertEqual(status["reason"], "closed")
                    self.assertEqual(status["samples"], [])
                    self.assertIs(status["perception_eligible"], False)
                self.assertEqual(accepted["state"], "OBSERVED_UNVERIFIED")
                self.assertIs(accepted["perception_eligible"], False)
                self.assertEqual(
                    [sample["message"] for sample in accepted["samples"]],
                    ["ATTITUDE", "LOCAL_POSITION_NED"],
                )
                for sample in accepted["samples"]:
                    self.assertEqual(sample["evidence"], "external_unverified")
                    self.assertIs(sample["authenticated"], False)
                    self.assertIsNone(sample["capture_ns"])
                    self.assertIsNone(sample["link_id"])
                    self.assertIsNone(sample["signature_timestamp"])
                self.assertEqual(report["corrupt_state"], "UNKNOWN")
                self.assertEqual(report["corrupt_reason"], "invalid_packet")
                self.assertEqual(report["corrupt_samples"], 0)
                self.assertFalse(report["perception_eligible"])
                self.assertEqual(report["closed_reason"], "closed")
                self.assertEqual(report["pymavlink_version"], "2.4.50")
                self.assertEqual(report["lxml_loaded"], False)
                self.assertEqual(report["fastcrc_loaded"], mode == "installed")
                self.assertEqual(
                    set(report["phase_ns"]),
                    {"adapter_import", "first_constructor", "second_constructor"},
                )
                for duration in report["phase_ns"].values():
                    self.assertIs(type(duration), int)
                    self.assertGreaterEqual(duration, 0)
                self.assertTrue(report["module_sha256"])
                self.assertIn("pymavlink.dialects.v20.common", report["module_sha256"])
                source = (
                    Path(__file__).resolve().parents[2]
                    / "integrations/edge/aethron_edge/telemetry/mavlink.py"
                )
                self.assertEqual(
                    report["module_sha256"]["aethron_edge.telemetry.mavlink"],
                    hashlib.sha256(source.read_bytes()).hexdigest(),
                )
                self.assertNotIn("/home/", result.stdout.decode())

    def test_unknown_mode_is_refused_without_measurement_receipt(self):
        result = subprocess.run(  # nosec B603
            [sys.executable, "-I", str(self.probe), "unknown"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()
