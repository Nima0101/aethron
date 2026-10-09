"""Explicit policy binding cannot initialize or reset replay state."""

import contextlib
import hashlib
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron_edge.cli import main
from aethron_edge.telemetry.boot_authority import MAVLINK_EPOCH_NS
from aethron_edge.telemetry.signing import SigningTrust, provision_replay


class PolicyCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journal = self.root / "replay.db"
        self.policy = self.root / "policy.json"
        self.policy.write_text(
            json.dumps(
                {
                    "version": 1,
                    "system_id": 1,
                    "component_id": 2,
                    "key_hex": bytes(range(32)).hex(),
                    "link_id": 7,
                    "not_before_unix_ns": MAVLINK_EPOCH_NS,
                    "not_after_unix_ns": MAVLINK_EPOCH_NS + 100_000_000_000,
                    "lease_ns": 10_000_000_000,
                    "drift_budget_ns": 1_000_000,
                }
            )
        )
        self.policy.chmod(0o600)
        self.config = self.root / "appliance.json"
        self.raw = {
            "version": 1,
            "runtime_mode": "interactive",
            "status_file": "status.json",
            "profiles": [{"name": "camera", "driver": "replay", "address": "unused"}],
            "telemetry": [
                {
                    "name": "flight",
                    "system_id": 1,
                    "component_id": 2,
                    "port": 14550,
                    "clock_policy_file": "policy.json",
                    "replay_file": "replay.db",
                }
            ],
        }
        self.write()

    def write(self):
        self.config.write_text(json.dumps(self.raw))

    def provision(self):
        provision_replay(
            self.journal, SigningTrust(bytes(range(32)), 7, 123, 1, 2), system=1, component=2
        )

    def invoke(self, name="flight", *, command="bind-telemetry-policy", floor=None):
        out, err = io.StringIO(), io.StringIO()
        args = ["aethron-edge", command, "--config", str(self.config)]
        if floor is not None:
            args += ["--replay-floor", str(floor)]
        if name is not None:
            args += ["--name", name]
        with (
            patch.object(sys, "argv", args),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            try:
                main()
                code = 0
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_bind_existing_state_once_without_starting_runtime_or_issuing_grant(self):
        self.provision()
        with patch("aethron_edge.runtime.entrypoint.run") as run:
            code, out, err = self.invoke()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out), {"policy_bound": True, "authority_issued": False})
        run.assert_not_called()
        with contextlib.closing(sqlite3.connect(self.journal)) as db:
            self.assertEqual(db.execute("SELECT timestamp FROM replay").fetchone(), (123,))
            self.assertEqual(db.execute("SELECT boot FROM boot_authority").fetchone(), (None,))
        before = self.journal.read_bytes()
        self.assertEqual(self.invoke()[0], 2)
        self.assertEqual(self.journal.read_bytes(), before)

    def test_missing_journal_does_not_create_one_or_expose_details(self):
        code, out, err = self.invoke()
        self.assertEqual((code, out, err), (2, "", "telemetry_policy_binding_failed\n"))
        self.assertFalse(self.journal.exists())
        self.assertFalse((self.root / "status.json").exists())

    def test_bad_selection_or_manual_credential_cannot_bind(self):
        self.provision()
        before = self.journal.read_bytes()
        for name in ("unknown", None):
            self.assertEqual(self.invoke(name)[0], 2)
        item = self.raw["telemetry"][0]
        item.pop("clock_policy_file")
        item["credential_file"] = "unused"
        self.write()
        self.assertEqual(self.invoke()[0], 2)
        self.assertEqual(self.journal.read_bytes(), before)

    def test_appliance_mode_requires_signed_configuration_before_mutation(self):
        self.provision()
        before = self.journal.read_bytes()
        self.raw["runtime_mode"] = "appliance"
        self.write()
        self.assertEqual(self.invoke(), (2, "", "telemetry_policy_binding_failed\n"))
        self.assertEqual(self.journal.read_bytes(), before)

    def test_private_policy_mode_failure_does_not_change_journal(self):
        self.provision()
        before = self.journal.read_bytes()
        self.policy.chmod(0o644)
        self.assertEqual(self.invoke(), (2, "", "telemetry_policy_binding_failed\n"))
        self.assertEqual(self.journal.read_bytes(), before)

    def test_isolated_installed_cli_binds_without_source_imports(self):
        self.provision()
        args = [
            sys.executable,
            "-I",
            "-B",
            "-m",
            "aethron_edge",
            "bind-telemetry-policy",
            "--config",
            str(self.config),
            "--name",
            "flight",
        ]
        result = subprocess.run(
            args, cwd=self.root, capture_output=True, text=True, timeout=10, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout), {"policy_bound": True, "authority_issued": False}
        )
        before = self.journal.read_bytes()
        again = subprocess.run(
            args, cwd=self.root, capture_output=True, text=True, timeout=10, check=False
        )
        self.assertEqual(again.returncode, 2)
        self.assertEqual(again.stderr, "telemetry_policy_binding_failed\n")
        self.assertEqual(self.journal.read_bytes(), before)

    def test_isolated_installed_cli_initializes_once_without_source_imports(self):
        args = [
            sys.executable,
            "-I",
            "-B",
            "-m",
            "aethron_edge",
            "initialize-telemetry",
            "--config",
            str(self.config),
            "--name",
            "flight",
            "--replay-floor",
            "123",
        ]
        result = subprocess.run(
            args, cwd=self.root, capture_output=True, text=True, timeout=10, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"journal_created": True, "policy_bound": True, "authority_issued": False},
        )
        before = self.journal.read_bytes()
        again = subprocess.run(
            args, cwd=self.root, capture_output=True, text=True, timeout=10, check=False
        )
        self.assertEqual(again.returncode, 2)
        self.assertEqual(again.stderr, "initial_telemetry_provisioning_failed\n")
        self.assertEqual(self.journal.read_bytes(), before)

    def signed_configuration(self, *, replay_in_bundle=False):
        bundle = self.root / "bundle"
        bundle.mkdir()
        private, public = self.root / "test-only.pem", self.root / "test-only.pub"
        commands = [
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)],
            ["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)],
        ]
        for command in commands:
            subprocess.run(command, check=True, capture_output=True, timeout=10)
        if replay_in_bundle:
            self.journal = bundle / "replay.db"
        self.config = bundle / "appliance.json"
        (bundle / "fixture.jsonl").write_text(
            "fixture is signed, not executed during provisioning\n"
        )
        self.raw.update(
            runtime_mode="appliance", integrity_bundle=str(bundle), trust_root=str(public)
        )
        self.raw["profiles"][0]["address"] = "fixture.jsonl"
        self.raw["telemetry"][0].update(
            clock_policy_file=str(self.policy), replay_file=str(self.journal)
        )
        self.write()
        manifest = {
            "schema_version": 1,
            "version": 1,
            "config_version": 1,
            "files": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (self.config, bundle / "fixture.jsonl")
            },
        }
        (bundle / "manifest.json").write_text(json.dumps(manifest))
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                str(private),
                "-in",
                str(bundle / "manifest.json"),
                "-out",
                str(bundle / "manifest.sig"),
            ],
            check=True,
            capture_output=True,
            timeout=10,
        )
        return bundle

    def test_real_signed_appliance_configuration_provisions_without_starting_runtime(self):
        self.signed_configuration()
        with patch("aethron_edge.runtime.entrypoint.run") as run:
            self.assertEqual(self.invoke(command="initialize-telemetry", floor=123)[0], 0)
        run.assert_not_called()
        self.assertTrue(self.journal.is_file())

    def test_signed_input_tampering_rejects_before_initial_state_publication(self):
        bundle = self.signed_configuration()
        (bundle / "fixture.jsonl").write_text("tampered")
        self.assertEqual(
            self.invoke(command="initialize-telemetry", floor=123),
            (2, "", "initial_telemetry_provisioning_failed\n"),
        )
        self.assertFalse(self.journal.exists())

    def test_signed_configuration_cannot_publish_private_state_inside_bundle(self):
        self.signed_configuration(replay_in_bundle=True)
        self.assertEqual(
            self.invoke(command="initialize-telemetry", floor=123),
            (2, "", "initial_telemetry_provisioning_failed\n"),
        )
        self.assertFalse(self.journal.exists())

    def test_missing_signed_input_refuses_initialization(self):
        bundle = self.signed_configuration()
        (bundle / "fixture.jsonl").unlink()
        self.assertEqual(self.invoke(command="initialize-telemetry", floor=123)[0], 2)
        self.assertFalse(self.journal.exists())

    def test_initialization_requires_explicit_floor_and_never_overwrites(self):
        self.assertEqual(self.invoke(command="initialize-telemetry")[0], 2)
        self.assertFalse(self.journal.exists())
        code, out, err = self.invoke(command="initialize-telemetry", floor=123)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(
            json.loads(out),
            {"journal_created": True, "policy_bound": True, "authority_issued": False},
        )
        before = self.journal.read_bytes()
        self.assertEqual(self.invoke(command="initialize-telemetry", floor=0)[0], 2)
        self.assertEqual(self.journal.read_bytes(), before)

    def test_initialization_rejects_wrong_sender_and_unsigned_appliance(self):
        self.raw["telemetry"][0]["component_id"] = 3
        self.write()
        self.assertEqual(self.invoke(command="initialize-telemetry", floor=123)[0], 2)
        self.assertFalse(self.journal.exists())
        self.raw["telemetry"][0]["component_id"] = 2
        self.raw["runtime_mode"] = "appliance"
        self.write()
        self.assertEqual(self.invoke(command="initialize-telemetry", floor=123)[0], 2)
        self.assertFalse(self.journal.exists())

    def test_replay_floor_cannot_silently_turn_binding_into_initialization(self):
        self.assertEqual(self.invoke(floor=123)[0], 2)
        self.assertFalse(self.journal.exists())


if __name__ == "__main__":
    unittest.main()
