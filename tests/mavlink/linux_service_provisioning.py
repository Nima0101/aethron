"""Destructive only inside the explicitly disposable, isolated Linux test container.

Creates a synthetic service account and fixed-path fixture; never run on a host.
"""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


class ServiceProvisioning(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (
            sys.platform == "linux"
            and sys.flags.isolated
            and os.geteuid() == 0
            and os.environ.get("AETHRON_DISPOSABLE_PROVISION_TEST") == "1"
            and Path("/.dockerenv").is_file()
        ):
            raise RuntimeError("disposable_isolated_container_required")
        cls.bundle = Path("/opt/aethron")
        cls.state = Path("/var/lib/aethron")
        if list(cls.bundle.iterdir()) or list(cls.state.iterdir()):
            raise RuntimeError("empty_test_mounts_required")
        for cmd in (
            ["groupadd", "-g", "10000", "aethron"],
            [
                "useradd",
                "--no-log-init",
                "-M",
                "-u",
                "10000",
                "-g",
                "10000",
                "-d",
                "/nonexistent",
                "-s",
                "/usr/sbin/nologin",
                "aethron",
            ],
        ):
            subprocess.run(cmd, check=True, capture_output=True)
        cls.state.chmod(0o700)
        os.chown(cls.state, 10000, 10000)
        binary = cls.bundle / "venv/bin/python"
        binary.parent.mkdir(parents=True)
        shutil.copyfile(sys.executable, binary)
        binary.chmod(0o755)
        (cls.bundle / "fixture.jsonl").write_text("signed, not executed in provisioning\n")
        cls.private, cls.public = Path("/tmp/test-only.pem"), Path("/tmp/test-only.pub")
        for cmd in (
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(cls.private)],
            ["openssl", "pkey", "-in", str(cls.private), "-pubout", "-out", str(cls.public)],
        ):
            subprocess.run(cmd, check=True, capture_output=True)
        cls.public.chmod(0o644)
        spec = importlib.util.spec_from_file_location("installer", "/tests/install.py")
        cls.installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.installer)

    def setUp(self):
        self.policy = self.state / (self._testMethodName + ".json")
        self.journal = self.state / (self._testMethodName + ".db")
        self.policy.write_text(
            json.dumps(
                {
                    "version": 1,
                    "system_id": 1,
                    "component_id": 2,
                    "key_hex": bytes(range(32)).hex(),
                    "link_id": 7,
                    "not_before_unix_ns": 1420070400000000000,
                    "not_after_unix_ns": 1420070500000000000,
                    "lease_ns": 10000000000,
                    "drift_budget_ns": 1000000,
                }
            )
        )
        os.chown(self.policy, 10000, 10000)
        self.policy.chmod(0o600)
        self.config = self.bundle / "appliance.json"
        self.config.write_text(
            json.dumps(
                {
                    "version": 1,
                    "runtime_mode": "appliance",
                    "status_file": str(self.state / "status.json"),
                    "integrity_bundle": str(self.bundle),
                    "trust_root": str(self.public),
                    "profiles": [
                        {"name": "camera", "driver": "replay", "address": "fixture.jsonl"}
                    ],
                    "telemetry": [
                        {
                            "name": "flight",
                            "system_id": 1,
                            "component_id": 2,
                            "port": 14550,
                            "clock_policy_file": str(self.policy),
                            "replay_file": str(self.journal),
                        }
                    ],
                }
            )
        )
        files = [self.config, self.bundle / "fixture.jsonl", self.bundle / "venv/bin/python"]
        (self.bundle / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "version": 1,
                    "config_version": 1,
                    "files": {
                        str(p.relative_to(self.bundle)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in files
                    },
                }
            )
        )
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-rawin",
                "-inkey",
                str(self.private),
                "-in",
                str(self.bundle / "manifest.json"),
                "-out",
                str(self.bundle / "manifest.sig"),
            ],
            check=True,
            capture_output=True,
        )

    def test_installed_cli_publishes_as_service_uid_once(self):
        self.assertTrue(self.installer.provision_telemetry("flight", 123)["journal_created"])
        self.assertEqual((self.journal.stat().st_uid, self.journal.stat().st_gid), (10000, 10000))
        self.assertEqual(self.journal.stat().st_mode & 0o777, 0o600)
        before = self.journal.read_bytes()
        with self.assertRaises(ValueError):
            self.installer.provision_telemetry("flight", 0)
        self.assertEqual(self.journal.read_bytes(), before)
        self.assertFalse((self.state / "status.json").exists())

    def test_sil_provision_once_and_check_reuses_grant_without_reset(self):
        program = (
            "import importlib.util,json;from pathlib import Path;"
            "s=importlib.util.spec_from_file_location('sil','/tests/telemetry_boot_probe.py');"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
        )

        def run(operation):
            return subprocess.run(
                ["/opt/aethron/venv/bin/python", "-I", "-B", "-c", program + operation],
                user=10000,
                group=10000,
                extra_groups=[],
                umask=0o077,
                cwd="/",
                env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

        provision = "m.provision(Path('/opt/aethron/appliance.json'))"
        check = "print(json.dumps(m.check(Path('/opt/aethron/appliance.json'))))"
        self.assertNotEqual(run(check).returncode, 0)
        self.assertFalse(self.journal.exists())
        self.policy.unlink()  # Only the unused test policy; no journal exists.
        self.assertEqual(run(provision).returncode, 0)
        first = run(check)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["prior_boot"], "initial")
        second = run(check)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout)["prior_boot"], "same")
        before = self.journal.read_bytes()
        self.assertNotEqual(run(provision).returncode, 0)
        self.assertEqual(self.journal.read_bytes(), before)
        self.policy.unlink()
        self.assertNotEqual(run(check).returncode, 0)
        self.assertEqual(self.journal.read_bytes(), before)

    def test_missing_policy_never_creates_journal(self):
        self.policy.unlink()
        with self.assertRaises(ValueError):
            self.installer.provision_telemetry("flight", 123)
        self.assertFalse(self.journal.exists())

    def test_tampered_config_never_creates_journal(self):
        self.config.write_text(self.config.read_text() + " ")
        with self.assertRaises(ValueError):
            self.installer.provision_telemetry("flight", 123)
        self.assertFalse(self.journal.exists())

    def test_child_cannot_write_state_without_service_uid_permission(self):
        self.state.chmod(0o500)
        try:
            with self.assertRaises(ValueError):
                self.installer.provision_telemetry("flight", 123)
        finally:
            self.state.chmod(0o700)
        self.assertFalse(self.journal.exists())


if __name__ == "__main__":
    unittest.main()
