"""Private administrator clock policies; synthetic credentials, no hardware."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron_edge.config import load_config
from aethron_edge.runtime.supervisor import ApplianceSupervisor
from aethron_edge.runtime.updates import verify_configuration
from aethron_edge.telemetry import provisioning
from aethron_edge.telemetry.boot_authority import MAVLINK_EPOCH_NS, provision_boot_authority
from aethron_edge.telemetry.signing import SigningTrust, provision_replay

BOOT = "aeeeeeee-1111-4111-8111-111111111111"
WALL = MAVLINK_EPOCH_NS + 100_000_000_000


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "policy.json"
        self.document = {
            "version": 1,
            "system_id": 1,
            "component_id": 2,
            "key_hex": bytes(range(32)).hex(),
            "link_id": 7,
            "not_before_unix_ns": WALL - 1_000_000_000,
            "not_after_unix_ns": WALL + 60_000_000_000,
            "lease_ns": 10_000_000_000,
            "drift_budget_ns": 1_000_000,
        }
        self.write()
        self.config = self.root / "config.json"
        self.raw = {
            "version": 1,
            "status_file": str(self.root / "status.json"),
            "profiles": [{"name": "camera", "driver": "replay", "address": "missing.jsonl"}],
            "telemetry": [
                {
                    "name": "flight",
                    "system_id": 1,
                    "component_id": 2,
                    "port": 14551,
                    "clock_policy_file": "policy.json",
                    "replay_file": "replay.db",
                }
            ],
        }

    def write(self):
        self.path.write_text(json.dumps(self.document))
        self.path.chmod(0o600)

    def load(self):
        return provisioning.load_boot_policy(self.path, system=1, component=2)

    def config_load(self):
        self.config.write_text(json.dumps(self.raw))
        return load_config(self.config)

    def reject(self):
        with self.assertRaisesRegex(ValueError, "^invalid_telemetry_clock_policy$") as raised:
            self.load()
        self.assertNotIn(str(self.path), str(raised.exception))
        self.assertNotIn(self.document["key_hex"], str(raised.exception))

    def provision(self):
        provision_replay(
            self.root / "replay.db",
            SigningTrust(bytes(range(32)), 7, 0, 1, 2),
            system=1,
            component=2,
        )
        provision_boot_authority(self.root / "replay.db", self.load())

    def test_exact_policy_load_has_no_writes_or_boot_dependency(self):
        before = self.path.read_bytes()
        with patch.object(provisioning, "current_boot_id", side_effect=OSError):
            policy = self.load()
        self.assertEqual(policy.system_id, 1)
        self.assertEqual(policy.component_id, 2)
        self.assertEqual(policy.key, bytes(range(32)))
        self.assertNotIn(repr(policy.key), repr(policy))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_bad_schema_sender_bounds_and_key_are_refused(self):
        for field, value in [
            ("version", True),
            ("version", 2),
            ("system_id", 2),
            ("component_id", True),
            ("key_hex", "ab" * 33),
            ("key_hex", "AA" * 32),
            ("lease_ns", False),
            ("lease_ns", 0),
            ("link_id", 1.0),
            ("not_after_unix_ns", WALL - 2_000_000_000),
            ("drift_budget_ns", 1_000_000_001),
        ]:
            with self.subTest(field=field, value=value):
                original = self.document[field]
                self.document[field] = value
                self.write()
                self.reject()
                self.document[field] = original
        self.document["extra"] = "no"
        self.write()
        self.reject()
        self.document.pop("extra")
        self.write()
        for sender in (True, 0, 256, 1.0):
            with self.assertRaisesRegex(ValueError, "invalid_telemetry_clock_policy"):
                provisioning.load_boot_policy(self.path, system=sender, component=2)

    def test_malformed_duplicate_and_oversized_policy_refused(self):
        for raw in [b"[]", b"not JSON", b'{"version":1,"version":1}', b"[" * 2048, b" " * 2049]:
            self.path.write_bytes(raw)
            self.reject()

    def test_private_file_checks_are_shared_with_credential_loader(self):
        self.path.chmod(0o644)
        self.reject()
        self.path.chmod(0o600)
        self.root.chmod(0o755)
        self.reject()
        self.root.chmod(0o700)
        os.link(self.path, self.root / "hardlink")
        self.reject()
        (self.root / "hardlink").unlink()
        target = self.root / "actual"
        self.path.rename(target)
        self.path.symlink_to(target)
        self.reject()
        self.path.unlink()
        os.mkfifo(self.path, 0o600)
        self.reject()

    def test_config_requires_exactly_one_authority_source(self):
        config = self.config_load()
        self.assertIsNone(config.telemetry[0].credential_file)
        self.assertEqual(config.telemetry[0].clock_policy_file, str(self.path))
        self.raw["telemetry"][0]["credential_file"] = "credential.json"
        with self.assertRaises(ValueError):
            self.config_load()
        self.raw["telemetry"][0].pop("credential_file")
        self.raw["telemetry"][0].pop("clock_policy_file")
        with self.assertRaises(ValueError):
            self.config_load()

    def test_policy_must_stay_outside_distributable_bundle(self):
        self.raw.update(integrity_bundle=str(self.root), trust_root=str(self.root / "public.pem"))
        self.raw["telemetry"][0]["replay_file"] = "/outside/replay.db"
        config = self.config_load()
        with patch("aethron_edge.runtime.updates.verify_bundle", return_value={"files": {}}):
            with self.assertRaisesRegex(ValueError, "private_telemetry_state_in_bundle"):
                verify_configuration(config, self.config)

    def test_missing_journal_is_not_created_on_boot(self):
        runtime = ApplianceSupervisor()
        self.addCleanup(runtime.shutdown)
        with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
            runtime.boot(self.config_load())
        self.assertFalse(runtime.pipelines)
        self.assertFalse((self.root / "replay.db").exists())

    def test_boot_uses_bound_policy_and_does_not_renew_on_restart(self):
        self.provision()
        # Explicit synthetic clock providers only; the Linux consumer uses real clocks.
        from aethron_edge.telemetry.boot_authority import issue_boot_trust

        def issue(path, policy):
            return issue_boot_trust(
                path, policy, monotonic=lambda: 1000, realtime=lambda: WALL, boot_id=lambda: BOOT
            )

        grants = []
        for _ in range(2):
            runtime = ApplianceSupervisor()
            with (
                patch("aethron_edge.telemetry.boot_authority.issue_boot_trust", side_effect=issue),
                patch("aethron_edge.telemetry.worker.TelemetrySupervisor.start"),
                patch("aethron_edge.runtime.supervisor.RuntimePipeline.start"),
            ):
                try:
                    runtime.boot(self.config_load())
                    grants.append(runtime.telemetry["flight"].trust)
                finally:
                    runtime.shutdown()
        self.assertTrue(grants[0].boot_bound)
        self.assertEqual(grants[0], grants[1])

    def test_expired_or_replaced_policy_prevents_pipeline_start(self):
        self.provision()
        from aethron_edge.telemetry.boot_authority import issue_boot_trust

        for changed in (False, True):
            self.document["lease_ns"] = 5_000_000_000 if changed else 10_000_000_000
            self.write()
            runtime = ApplianceSupervisor()
            self.addCleanup(runtime.shutdown)

            def issue(path, policy):
                return issue_boot_trust(
                    path,
                    policy,
                    monotonic=lambda: 1000,
                    realtime=lambda: WALL + 60_000_000_000,
                    boot_id=lambda: BOOT,
                )

            with (
                patch("aethron_edge.runtime.supervisor.RuntimePipeline") as pipeline,
                patch("aethron_edge.telemetry.boot_authority.issue_boot_trust", side_effect=issue),
            ):
                with self.assertRaisesRegex(ValueError, "invalid_boot_authority"):
                    runtime.boot(self.config_load())
                pipeline.assert_not_called()


if __name__ == "__main__":
    unittest.main()
