"""Telemetry integration into the local appliance, without HTTP or hardware."""

import json
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron_edge.config import ApplianceConfig, load_config
from aethron_edge.runtime.supervisor import ApplianceSupervisor
from aethron_edge.runtime.updates import verify_configuration
from aethron_edge.telemetry.signing import SigningTrust, provision_replay
from pymavlink.dialects.v20 import common

ROOT = Path(__file__).resolve().parents[2]
BOOT = "aeeeeeee-1111-4111-8111-111111111111"


class ApplianceTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
            reservation.bind(("127.0.0.1", 0))
            self.port = reservation.getsockname()[1]
        self.raw = {
            "version": 1,
            "status_file": str(self.root / "status.json"),
            "profiles": [
                {
                    "name": "camera",
                    "driver": "replay",
                    "address": str(ROOT / "examples/temporal-blackout.jsonl"),
                }
            ],
            "telemetry": [
                {
                    "name": "flight",
                    "system_id": 1,
                    "component_id": 2,
                    "port": self.port,
                    "credential_file": "credential.json",
                    "replay_file": "replay.db",
                }
            ],
        }
        self.config_path = self.root / "config.json"
        self.config_path.write_text(json.dumps(self.raw))

    def provision(self):
        now = time.monotonic_ns()
        trust = SigningTrust(bytes(range(32)), 7, 10_000_000, now, now + 60_000_000_000)
        credential = {
            "version": 1,
            "boot_id": BOOT,
            "system_id": 1,
            "component_id": 2,
            "key_hex": trust.key.hex(),
            "link_id": trust.link_id,
            "timestamp_floor": trust.timestamp_floor,
            "issued_ns": trust.issued_ns,
            "valid_until_ns": trust.valid_until_ns,
        }
        path = self.root / "credential.json"
        path.write_text(json.dumps(credential))
        path.chmod(0o600)
        provision_replay(self.root / "replay.db", trust, system=1, component=2)

    def test_paths_preserve_symlink_for_private_loader_rejection(self):
        target = self.root / "target"
        target.write_text("not a credential")
        (self.root / "credential.json").symlink_to(target)
        config = load_config(self.config_path)
        self.assertEqual(config.telemetry[0].credential_file, str(self.root / "credential.json"))
        runtime = ApplianceSupervisor()
        self.addCleanup(runtime.shutdown)
        with self.assertRaisesRegex(ValueError, "invalid_telemetry_credential"):
            runtime.boot(config)
        self.assertFalse(runtime.pipelines)

    def test_duplicate_names_ports_and_unbounded_counts_are_rejected(self):
        ApplianceConfig.model_validate(self.raw)
        for change in ("name", "port", "count"):
            raw = json.loads(json.dumps(self.raw))
            second = dict(raw["telemetry"][0], name="other", port=self.port % 65535 + 1)
            if change == "name":
                second["name"] = "flight"
            elif change == "port":
                second["port"] = self.port
            raw["telemetry"].append(second)
            if change == "count":
                raw["telemetry"].append(dict(second, name="third"))
            with self.subTest(change=change), self.assertRaises(ValueError):
                ApplianceConfig.model_validate(raw)

    def test_private_credentials_and_journal_cannot_be_in_distributable_bundle(self):
        self.raw.update(integrity_bundle=str(self.root), trust_root=str(self.root / "public.pem"))
        self.config_path.write_text(json.dumps(self.raw))
        config = load_config(self.config_path)
        with patch(
            "aethron_edge.runtime.updates.verify_bundle",
            return_value={"files": {"config.json": "hash"}},
        ):
            with self.assertRaisesRegex(ValueError, "private_telemetry_state_in_bundle"):
                verify_configuration(config, self.config_path)

    def test_expired_credential_prevents_start_without_recreating_state(self):
        self.provision()
        path = self.root / "credential.json"
        value = json.loads(path.read_bytes())
        value.update(issued_ns=1, valid_until_ns=2)
        path.write_text(json.dumps(value))
        journal = (self.root / "replay.db").read_bytes()
        runtime = ApplianceSupervisor()
        self.addCleanup(runtime.shutdown)
        with patch("aethron_edge.telemetry.provisioning.current_boot_id", return_value=BOOT):
            with self.assertRaisesRegex(ValueError, "invalid_telemetry_credential"):
                runtime.boot(load_config(self.config_path))
        self.assertFalse(runtime.pipelines)
        self.assertEqual((self.root / "replay.db").read_bytes(), journal)

    def test_cli_shutdown_owns_telemetry_after_http_failure(self):
        from aethron_edge.cli import main

        self.provision()
        self.raw["runtime_mode"] = "interactive"
        self.config_path.write_text(json.dumps(self.raw))
        sources = []

        def failed_http(config, *, supervisor):
            sources.extend(supervisor.telemetry.values())
            self.assertEqual(len(sources), 1)
            self.assertTrue(sources[0]._thread.is_alive())
            raise RuntimeError("test_http_failure")

        with (
            patch("aethron_edge.telemetry.provisioning.current_boot_id", return_value=BOOT),
            patch("aethron_edge.service.app.serve", side_effect=failed_http),
            patch.object(sys, "argv", ["aethron-edge", "run", "--config", str(self.config_path)]),
            self.assertRaisesRegex(RuntimeError, "test_http_failure"),
        ):
            main()
        self.assertTrue(sources)
        self.assertTrue(all(not source._thread.is_alive() for source in sources))
        self.assertTrue(all(source.process is None for source in sources))

    def test_appliance_receives_without_http_and_closes_owned_worker(self):
        self.provision()
        runtime = ApplianceSupervisor()
        self.addCleanup(runtime.shutdown)
        with patch("aethron_edge.telemetry.provisioning.current_boot_id", return_value=BOOT):
            runtime.boot(load_config(self.config_path))
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(sender.close)
        deadline = time.monotonic() + 10
        seq = 0
        last_iteration = time.monotonic()
        max_sender_gap_ms = 0
        while time.monotonic() < deadline:
            iteration = time.monotonic()
            max_sender_gap_ms = max(max_sender_gap_ms, (iteration - last_iteration) * 1000)
            last_iteration = iteration
            status = runtime.status(time.monotonic_ns())
            if status["telemetry"]["flight"]["authenticated"]:
                break
            encoder = common.MAVLink(None, srcSystem=1, srcComponent=2)
            encoder.seq = seq % 256
            encoder.signing.secret_key = bytes(range(32))
            encoder.signing.sign_outgoing = True
            encoder.signing.link_id = 7
            encoder.signing.timestamp = 10_000_001 + seq
            packet = common.MAVLink_attitude_message(10 + seq, 0.1, 0.2, 0.3, 0, 0, 0).pack(encoder)
            sender.sendto(packet, ("127.0.0.1", self.port))
            seq += 1
            time.sleep(0.05)
        else:
            self.fail(
                f"appliance_telemetry_deadline: sent={seq}, "
                f"max_sender_gap_ms={max_sender_gap_ms:.3f}, status={status}"
            )
        self.assertFalse(status["qualified"])
        self.assertFalse(status["telemetry"]["flight"]["perception_eligible"])
        self.assertNotIn("values", status["telemetry"]["flight"])
        process = runtime.telemetry["flight"].process
        runtime.shutdown()
        self.assertFalse(process.is_alive())
        self.assertEqual(json.loads((self.root / "status.json").read_bytes())["state"], "stopped")


if __name__ == "__main__":
    unittest.main()
