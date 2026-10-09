"""ROS SIL assembly must preserve raw coverage and require separate boot evidence."""

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


class RosGuestAssembly(unittest.TestCase):
    def test_ros_staging_keeps_independent_signed_config_and_raw_coverage(self):
        from aethron_edge.config import load_config
        from aethron_edge.sensors.ros_authority import read_ros_manifest

        prepare = load("prepare", "packaging/appliance/image/prepare.py")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            required = prepare.stage_inputs(root, ros=True)
            self.assertEqual(required, {"raw-depth": "recorded"})
            raw = load_config(root / "appliance.json")
            ros = load_config(root / "ros-appliance.json")
            self.assertEqual([p.driver for p in raw.profiles], ["replay", "sensor-replay"])
            self.assertEqual(len(ros.profiles), 1)
            self.assertEqual(ros.profiles[0].driver, "sensor-ros")
            self.assertNotEqual(raw.status_file, ros.status_file)
            self.assertNotEqual(raw.port, ros.port)
            self.assertEqual(ros.integrity_bundle, str(root.resolve()))
            manifest = read_ros_manifest(ros.profiles[0])
            self.assertEqual(manifest.renewal, "software_fixture")
            self.assertEqual(manifest.valid_for_ns, 4_000_000_000)
            self.assertEqual(manifest.clock_drift_budget_ns, 1_000_000)
            self.assertIn(
                "EnvironmentFile=/opt/aethron/venv/ros.env",
                (root / "ros-runtime.service").read_text(),
            )
            self.assertIn("aethron-ros-check.service", (root / "probe.service").read_text())
            self.assertIn("/opt/aethron/venv/bin/python", (root / "probe.service").read_text())

    def test_prior_boot_failed_or_incomplete_ros_result_is_refused(self):
        probe = load("ros_boot_probe", "packaging/appliance/image/ros_boot_probe.py")
        value = {
            "boot_id": "current-boot",
            "service_manager": "systemd",
            "processing_observed": True,
            "source_expiry_verified": True,
            "reconnect_cannot_revive": True,
            "explicit_restart_revalidated": True,
            "source_rewind_verified": True,
            "clock_restore_cannot_revive": True,
            "continuous_availability_qualified": False,
            "hardware_qualified": False,
            "scene_state": "UNKNOWN",
            "viewers": 0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.json"
            for change in (
                {"boot_id": "previous-boot"},
                {"hardware_qualified": True},
                {"source_rewind_verified": False},
                {"viewers": True},
                {"service_manager": "cli"},
                {"processing_observed": 1},
            ):
                path.write_text(json.dumps(dict(value, **change)))
                with self.subTest(change=change), self.assertRaises(ValueError):
                    probe.read_boot_result(path, "current-boot")
            path.write_text(json.dumps(value))
            self.assertEqual(probe.read_boot_result(path, "current-boot"), value)
            path.write_text(" " * 4097)
            with self.assertRaises(ValueError):
                probe.read_boot_result(path, "current-boot")

    def test_lifecycle_must_be_required_on_both_boots_not_borrowed_from_raw(self):
        boot = load("boot", "scripts/appliance_boot_e2e.py")
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
            path.write_text("".join("AETHRON_SIL " + json.dumps(r) + "\n" for r in rows))
            self.assertEqual(
                boot.inspect_evidence(path, require_ros_lifecycle=True)["status"], "failed"
            )
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
                    "continuous_availability_qualified": False,
                    "hardware_qualified": False,
                    "scene_state": "UNKNOWN",
                    "viewers": 0,
                }

            def inspect():
                path.write_text("".join("AETHRON_SIL " + json.dumps(r) + "\n" for r in rows))
                return boot.inspect_evidence(path, require_ros_lifecycle=True)["status"]

            self.assertEqual(inspect(), "passed")
            original = rows[1]["ros_lifecycle"].copy()
            for change in (
                {"boot_id": "0"},
                {"source_expiry_verified": False},
                {"continuous_availability_qualified": True},
                {"viewers": True},
                {"service_manager": "cli"},
                {"processing_observed": 1},
            ):
                rows[1]["ros_lifecycle"] = dict(original, **change)
                with self.subTest(change=change):
                    self.assertEqual(inspect(), "failed")

    def test_guest_disables_all_login_generators_and_exposes_probe_errors(self):
        recipe = (ROOT / "packaging/appliance/image/RosGuest.Containerfile").read_text()
        self.assertIn(
            "systemctl mask getty@.service serial-getty@.service console-getty.service", recipe
        )
        unit = (ROOT / "packaging/appliance/image/aethron-ros-check.service").read_text()
        self.assertIn("StandardError=journal+console", unit)

    def test_fixed_systemd_unit_exit_and_cleanup_are_observed(self):
        from subprocess import CompletedProcess
        from unittest.mock import patch

        probe = load("ros_boot_probe", "packaging/appliance/image/ros_boot_probe.py")
        service = probe.SystemdFixture()
        with patch.object(
            probe.subprocess, "run", return_value=CompletedProcess([], 0, "active\n")
        ) as run:
            service.start()
            self.assertIsNone(service.poll())
            service.stop()
            self.assertEqual(
                [c.args[0] for c in run.call_args_list],
                [
                    ["/usr/bin/systemctl", "start", "aethron-ros-fixture.service"],
                    [
                        "/usr/bin/systemctl",
                        "show",
                        "--property=ActiveState",
                        "--value",
                        "aethron-ros-fixture.service",
                    ],
                    ["/usr/bin/systemctl", "stop", "aethron-ros-fixture.service"],
                ],
            )
            run.return_value = CompletedProcess([], 0, "failed\n")
            self.assertEqual(service.poll(), 1)
