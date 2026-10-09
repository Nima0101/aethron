"""Optional boot evidence must be current, explicit and never self-provisioning."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TelemetryBootTests(unittest.TestCase):
    def test_missing_stale_incomplete_or_overclaiming_boot_evidence_is_refused(self):
        probe = load("telemetry_probe", "packaging/appliance/image/telemetry_boot_probe.py")
        good = {
            "boot_id": "current",
            "kind": "synthetic_direct_sdk",
            "hardware_qualified": False,
            "continuous_availability_qualified": False,
            "grant_preserved": True,
            "counter_advanced": True,
            "signed_packet_accepted": True,
            "duplicate_rejected": True,
            "prior_boot": "initial",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.json"
            with self.assertRaises(OSError):
                probe.read_boot_result(path, "current")
            for change in (
                {"boot_id": "old"},
                {"counter_advanced": 1},
                {"hardware_qualified": True},
                {"kind": "live"},
                {"prior_boot": "unknown"},
            ):
                path.write_text(json.dumps(good | change))
                with self.assertRaises(ValueError):
                    probe.read_boot_result(path, "current")
            path.write_text(json.dumps(good))
            self.assertEqual(probe.read_boot_result(path, "current"), good)
            path.write_text(" " * 4097)
            with self.assertRaises(ValueError):
                probe.read_boot_result(path, "current")

    def test_host_requires_telemetry_on_both_distinct_boots_and_no_reset(self):
        host = load("host_boot", "scripts/appliance_boot_e2e.py")
        rows = [
            {"event": "result", "boot": 1, "processing_continued": True},
            {
                "event": "result",
                "boot": 2,
                "processing_continued": True,
                "seconds": 3600,
                "worker_fault_injected": True,
                "processing_resumed_after_fault": True,
                "updated_runtime_processing": True,
                "drops": {
                    "capture_sequence_gaps": 0,
                    "mailbox_overwritten": 0,
                    "mailbox_rejected": 0,
                },
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "serial.log"

            def inspect():
                path.write_text("".join("AETHRON_SIL " + json.dumps(r) + "\n" for r in rows))
                return host.inspect_evidence(path, require_telemetry_boot=True)["status"]

            self.assertEqual(inspect(), "failed")
            for i, row in enumerate(rows):
                row["telemetry_boot"] = {
                    "boot_id": str(i),
                    "kind": "synthetic_direct_sdk",
                    "prior_boot": "initial" if i == 0 else "different",
                    "hardware_qualified": False,
                    "continuous_availability_qualified": False,
                    "grant_preserved": True,
                    "counter_advanced": True,
                    "signed_packet_accepted": True,
                    "duplicate_rejected": True,
                }
            self.assertEqual(inspect(), "passed")
            good = rows[1]["telemetry_boot"].copy()
            for change in (
                {"boot_id": "0"},
                {"prior_boot": "initial"},
                {"prior_boot": "same"},
                {"counter_advanced": 1},
                {"duplicate_rejected": False},
                {"hardware_qualified": True},
                {"kind": "live"},
            ):
                rows[1]["telemetry_boot"] = good | change
                self.assertEqual(inspect(), "failed")
            rows[1]["telemetry_boot"] = good
            for i, row in enumerate(rows):
                row["ros_lifecycle"] = {
                    "boot_id": str(i),
                    "service_manager": "systemd",
                    "processing_observed": True,
                    "source_expiry_verified": True,
                    "reconnect_cannot_revive": True,
                    "explicit_restart_revalidated": True,
                    "source_rewind_verified": True,
                    "clock_restore_cannot_revive": True,
                    "hardware_qualified": False,
                    "continuous_availability_qualified": False,
                    "scene_state": "UNKNOWN",
                    "viewers": 0,
                }
            inspect()
            self.assertEqual(
                host.inspect_evidence(
                    path, require_ros_lifecycle=True, require_telemetry_boot=True
                )["status"],
                "passed",
            )
            rows[1]["ros_lifecycle"]["boot_id"] = "unrelated"
            inspect()
            self.assertEqual(
                host.inspect_evidence(
                    path, require_ros_lifecycle=True, require_telemetry_boot=True
                )["status"],
                "failed",
            )

    def test_optional_staging_separates_one_time_provisioning_from_boot_check(self):
        prepare = load("prepare", "packaging/appliance/image/prepare.py")
        with tempfile.TemporaryDirectory() as tmp:
            context = Path(tmp)
            prepare.stage_inputs(context, ros=True)
            before = (context / "appliance.json").read_bytes()
            prepare.stage_mavlink_probe(context)
            self.assertEqual((context / "appliance.json").read_bytes(), before)
            config = json.loads((context / "telemetry-appliance.json").read_text())
            self.assertEqual(config["runtime_mode"], "appliance")
            self.assertEqual(
                config["telemetry"][0]["replay_file"], "/var/lib/aethron-telemetry/replay.db"
            )
            unit = (context / "telemetry-check.service").read_text()
            self.assertIn("User=aethron", unit)
            self.assertNotIn("provision", unit)
            self.assertIn("telemetry_boot_probe.py check", unit)
            recipe = (context / "Guest.Containerfile").read_text()
            self.assertIn("telemetry_boot_probe.py provision", recipe)
            self.assertLess(
                recipe.index("/tmp/sign.py &&"), recipe.index("telemetry_boot_probe.py provision")
            )
            self.assertIn(
                "aethron-telemetry-check.service", (context / "probe.service").read_text()
            )


if __name__ == "__main__":
    unittest.main()
