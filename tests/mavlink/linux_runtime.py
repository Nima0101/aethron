"""Explicit installed Linux consumer; real kernel boot ID, synthetic signing key."""

import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from aethron_edge.config import ApplianceConfig
from aethron_edge.runtime.supervisor import ApplianceSupervisor
from aethron_edge.telemetry.provisioning import current_boot_id, load_trust
from aethron_edge.telemetry.signing import SigningTrust, provision_replay
from pymavlink.dialects.v20 import common


class LinuxRuntime(unittest.TestCase):
    def setUp(self):
        self.assertEqual(sys.platform, "linux")
        self.assertTrue(sys.flags.isolated)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "credential.json"
        now = time.monotonic_ns()
        self.trust = SigningTrust(bytes(range(32)), 7, 10_000_000, now, now + 60_000_000_000)
        self.document = {
            "version": 1,
            "boot_id": current_boot_id(),
            "system_id": 1,
            "component_id": 1,
            "key_hex": self.trust.key.hex(),
            "link_id": 7,
            "timestamp_floor": 10_000_000,
            "issued_ns": now,
            "valid_until_ns": self.trust.valid_until_ns,
        }
        self.path.write_text(json.dumps(self.document))
        self.path.chmod(0o600)
        self.journal = self.root / "replay.db"
        provision_replay(self.journal, self.trust, system=1, component=1)

    def test_kernel_boot_binding_and_restart_preserve_original_grant(self):
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        self.assertEqual(self.document["boot_id"], boot)
        self.assertEqual(load_trust(self.path, system=1, component=1), self.trust)
        self.assertEqual(load_trust(self.path, system=1, component=1), self.trust)
        self.document["boot_id"] = "00000000-0000-0000-0000-000000000000"
        self.path.write_text(json.dumps(self.document))
        with self.assertRaisesRegex(ValueError, "invalid_telemetry_credential"):
            load_trust(self.path, system=1, component=1)

    def test_boot_issuer_uses_kernel_identity_and_preserves_grant_across_calls(self):
        import sqlite3
        from contextlib import closing

        from aethron_edge.telemetry.boot_authority import (
            BootClockPolicy,
            issue_boot_trust,
            provision_boot_authority,
        )
        from aethron_edge.telemetry.signing import SignedTelemetry

        now = time.time_ns()
        policy = BootClockPolicy(
            self.trust.key,
            1,
            1,
            7,
            now - 1_000_000_000,
            now + 60_000_000_000,
            5_000_000_000,
            1_000_000,
        )
        provision_boot_authority(self.journal, policy)
        grant = issue_boot_trust(self.journal, policy)
        self.assertTrue(grant.boot_bound)
        self.assertEqual(issue_boot_trust(self.journal, policy), grant)
        with closing(sqlite3.connect(self.journal)) as connection:
            boot = connection.execute("SELECT boot FROM boot_authority").fetchone()[0]
        self.assertEqual(boot, current_boot_id())
        source = SignedTelemetry(1, 1, trust=grant, replay_path=self.journal)
        self.addCleanup(source.close)
        encoder = common.MAVLink(None, srcSystem=1, srcComponent=1)
        encoder.signing.secret_key = self.trust.key
        encoder.signing.sign_outgoing = True
        encoder.signing.link_id = 7
        encoder.signing.timestamp = grant.timestamp_floor + 1
        source.ingest(common.MAVLink_attitude_message(10, 0.1, 0.2, 0.3, 0, 0, 0).pack(encoder))
        self.assertTrue(source.snapshot().samples)
        self.assertFalse(source.snapshot().perception_eligible)

    def test_installed_appliance_receives_offline_and_shuts_down(self):
        self.appliance_receives(clock_policy=False)

    def test_installed_policy_appliance_receives_offline_and_shuts_down(self):
        self.appliance_receives(clock_policy=True)

    def test_initial_provisioning_cli_then_offline_policy_runtime(self):
        self.appliance_receives(clock_policy=True, initialize=True)

    def appliance_receives(self, *, clock_policy, initialize=False):
        if clock_policy:
            from aethron_edge.telemetry.boot_authority import provision_boot_authority
            from aethron_edge.telemetry.provisioning import load_boot_policy

            wall = time.time_ns()
            self.path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "system_id": 1,
                        "component_id": 1,
                        "key_hex": self.trust.key.hex(),
                        "link_id": 7,
                        "not_before_unix_ns": wall - 1_000_000_000,
                        "not_after_unix_ns": wall + 60_000_000_000,
                        "lease_ns": 30_000_000_000,
                        "drift_budget_ns": 1_000_000,
                    }
                )
            )
            policy = load_boot_policy(self.path, system=1, component=1)
            if initialize:
                # Use a new destination; never remove/reset previously provisioned state.
                self.journal = self.root / "initial-replay.db"
            else:
                provision_boot_authority(self.journal, policy)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        config = ApplianceConfig.model_validate(
            {
                "version": 1,
                # This local consumer has no signed bundle; do not bypass the CLI gate.
                "runtime_mode": "interactive",
                "status_file": str(self.root / "status.json"),
                "profiles": [
                    {"name": "replay", "driver": "replay", "address": "/opt/aethron/fixture.jsonl"}
                ],
                "telemetry": [
                    {
                        "name": "flight",
                        "system_id": 1,
                        "component_id": 1,
                        "port": port,
                        ("clock_policy_file" if clock_policy else "credential_file"): str(
                            self.path
                        ),
                        "replay_file": str(self.journal),
                    }
                ],
            }
        )
        if initialize:
            config_path = self.root / "initial-config.json"
            config_path.write_text(config.model_dump_json())
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-m",
                    "aethron_edge",
                    "initialize-telemetry",
                    "--config",
                    str(config_path),
                    "--name",
                    "flight",
                    "--replay-floor",
                    "10000000",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)["authority_issued"])
        runtime = ApplianceSupervisor()
        self.addCleanup(runtime.shutdown)
        runtime.boot(config)
        grant = runtime.telemetry["flight"].trust
        self.assertEqual(grant.boot_bound, clock_policy)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
            deadline, seq = time.monotonic() + 10, 0
            while time.monotonic() < deadline:
                status = runtime.status(time.monotonic_ns())
                if status["telemetry"]["flight"]["authenticated"] and status["processed"]:
                    break
                encoder = common.MAVLink(None, srcSystem=1, srcComponent=1)
                encoder.seq = seq % 256
                encoder.signing.secret_key = self.trust.key
                encoder.signing.sign_outgoing = True
                encoder.signing.link_id = 7
                encoder.signing.timestamp = grant.timestamp_floor + 1 + seq
                packet = common.MAVLink_attitude_message(10 + seq, 0.1, 0.2, 0.3, 0, 0, 0).pack(
                    encoder
                )
                sender.sendto(packet, ("127.0.0.1", port))
                seq += 1
                time.sleep(0.05)
            else:
                self.fail(f"linux_runtime_deadline: {status}")
        self.assertFalse(status["qualified"])
        self.assertFalse(status["telemetry"]["flight"]["perception_eligible"])
        child = runtime.telemetry["flight"].process
        if clock_policy:
            # No more packets: the owned clock monitor must notice revocation
            # independently of a viewer or another receiver commit.
            import sqlite3
            from contextlib import closing

            with closing(sqlite3.connect(self.journal)) as connection:
                connection.execute("UPDATE boot_authority SET revoked=1 WHERE id=1")
                connection.commit()
            time.sleep(0.12)
            self.assertFalse(
                runtime.status(time.monotonic_ns())["telemetry"]["flight"]["authenticated"]
            )
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                status = runtime.status(time.monotonic_ns())
                if status["telemetry"]["flight"]["state"] == "fault":
                    break
                time.sleep(0.01)
            else:
                self.fail(f"idle_revocation_deadline: {status}")
            self.assertEqual(runtime.telemetry["flight"].trust, grant)
        runtime.shutdown()
        self.assertFalse(child.is_alive())
        self.assertEqual(json.loads((self.root / "status.json").read_text())["state"], "stopped")


if __name__ == "__main__":
    unittest.main()
