import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("boot_check", ROOT / "scripts/appliance_boot_e2e.py")
boot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(boot)


class ArtifactGate(unittest.TestCase):
    def test_boot_only_short_soak_or_stalled_recovery_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "serial.log"
            first = {"event": "result", "boot": 1, "processing_continued": True}
            second = {
                "event": "result",
                "boot": 2,
                "processing_continued": True,
                "seconds": 3600,
                "worker_fault_injected": True,
                "processing_resumed_after_fault": True,
                "updated_runtime_processing": True,
                "drops": {
                    "capture_sequence_gaps": 0,
                    "mailbox_overwritten": 4,
                    "mailbox_rejected": 1,
                },
            }
            for changed in (
                {"seconds": 3599},
                {"drops": {}},
                {
                    "drops": {
                        "capture_sequence_gaps": -1,
                        "mailbox_overwritten": 0,
                        "mailbox_rejected": 0,
                    }
                },
                {"processing_resumed_after_fault": False},
                {"worker_fault_injected": False},
                {"updated_runtime_processing": False},
            ):
                path.write_text(
                    "AETHRON_SIL "
                    + json.dumps(first)
                    + "\nAETHRON_SIL "
                    + json.dumps(dict(second, **changed))
                    + "\n"
                )
                self.assertEqual(boot.inspect_evidence(path)["status"], "failed")
            path.write_text(
                "AETHRON_SIL " + json.dumps(first) + "\nAETHRON_SIL " + json.dumps(second) + "\n"
            )
            self.assertEqual(boot.inspect_evidence(path)["status"], "passed")

    def test_declared_raw_profile_cannot_borrow_proposal_success(self):
        first = {"event": "result", "boot": 1, "processing_continued": True}
        second = {
            "event": "result",
            "boot": 2,
            "processing_continued": True,
            "seconds": 3600,
            "worker_fault_injected": True,
            "processing_resumed_after_fault": True,
            "updated_runtime_processing": True,
            "drops": {"capture_sequence_gaps": 0, "mailbox_overwritten": 0, "mailbox_rejected": 0},
        }
        sensor = {
            "source_evidence": "recorded",
            "batches_observed": 100,
            "processing_observed": True,
            "processing_at_end": True,
            "processing_resumed_after_fault": True,
            "updated_runtime_processing": True,
            "unavailable_samples": 7,
            "fault_samples": 1,
            "invalid_samples": 0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "serial.log"

            def check(a, b, **kwargs):
                path.write_text(
                    "AETHRON_SIL " + json.dumps(a) + "\nAETHRON_SIL " + json.dumps(b) + "\n"
                )
                return boot.inspect_evidence(
                    path, required_sensors={"raw-depth": "recorded"}, **kwargs
                )["status"]

            self.assertEqual(check(first, second), "failed")
            first["sensor_profiles"] = {"raw-depth": sensor}
            second["sensor_profiles"] = {"raw-depth": sensor}
            self.assertEqual(check(first, second), "passed")
            for change in (
                {"batches_observed": 0},
                {"batches_observed": True},
                {"processing_at_end": False},
                {"processing_resumed_after_fault": False},
                {"updated_runtime_processing": False},
                {"processing_observed": "yes"},
                {"source_evidence": "external_unverified"},
                {"fault_samples": -1},
            ):
                with self.subTest(change=change):
                    bad = dict(second, sensor_profiles={"raw-depth": dict(sensor, **change)})
                    self.assertEqual(check(first, bad), "failed")
            self.assertEqual(check(first, second, exit_code=124), "failed")
            check(first, second)
            with path.open("a") as stream:
                stream.write('AETHRON_SIL {"event":"probe_failed","error_type":"RuntimeError"}\n')
            self.assertEqual(boot.inspect_evidence(path)["status"], "failed")
