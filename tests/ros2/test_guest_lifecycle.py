"""Installed guest-only signed CLI: source loss and timestamp discontinuity."""

import hashlib
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class GuestLifecycle(unittest.TestCase):
    def test_isolated_interpreter_loads_provisioned_sdk_without_pythonpath(self):
        import os

        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        result = subprocess.run(
            [sys.executable, "-I", "-c", "import rclpy; from sensor_msgs.msg import Image"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_sdk_provisioning_is_idempotent_and_refuses_conflicting_paths(self):
        from provision_ros_sdk import provision

        target = provision()
        original = target.read_text()
        self.assertEqual(provision(), target)
        try:
            target.write_text("/untrusted/path\n")
            with self.assertRaisesRegex(ValueError, "existing_sdk_path_conflict"):
                provision()
            self.assertEqual(target.read_text(), "/untrusted/path\n")
        finally:
            target.write_text(original)

    def test_sdk_provisioning_never_modifies_global_python(self):
        import provision_ros_sdk

        result = subprocess.run(
            ["/usr/bin/python3", "-I", provision_ros_sdk.__file__],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dedicated_python312_venv_required", result.stderr)

    def test_signed_installed_cli_loss_reconnect_restart_and_clock_rewind(self):
        from ros_lifecycle_probe import run_scenario
        from test_sensor_ros_appliance import fixture

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "bundle"
            bundle.mkdir()
            config_path, _ = fixture(
                bundle, valid_for_ns=4_000_000_000, version=2, renewal="software_fixture"
            )
            private, public = root / "test.pem", root / "test.pub"
            subprocess.run(
                ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)],
                check=True,
                capture_output=True,
            )
            private.chmod(0o600)
            subprocess.run(
                ["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)],
                check=True,
                capture_output=True,
            )
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            config = json.loads(config_path.read_text())
            config.update(
                status_file=str(root / "status.json"),
                integrity_bundle=".",
                trust_root=str(public),
                port=port,
            )
            config_path.write_text(json.dumps(config))
            manifest = {
                "schema_version": 1,
                "version": 1,
                "config_version": 1,
                "files": {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.iterdir()
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
            )
            result = run_scenario(config_path, python=sys.executable)
            self.assertTrue(result["processing_observed"])
            self.assertTrue(result["source_expiry_verified"])
            self.assertTrue(result["reconnect_cannot_revive"])
            self.assertTrue(result["explicit_restart_revalidated"])
            self.assertTrue(result["source_rewind_verified"])
            self.assertTrue(result["clock_restore_cannot_revive"])
            self.assertFalse(result["continuous_availability_qualified"])
            self.assertFalse(result["hardware_qualified"])
