"""Administrator provisioning must drop privileges and never become boot recovery."""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "appliance_installer", ROOT / "packaging/appliance/install.py"
)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class TelemetryInstallerTests(unittest.TestCase):
    def invoke(self, name="flight", floor=123):
        return installer.provision_telemetry(name, floor)

    def account(self):
        return patch("pwd.getpwnam", return_value=SimpleNamespace(pw_uid=1234, pw_gid=1234))

    def test_provisioning_drops_privileges_and_uses_only_fixed_installed_paths(self):
        result = subprocess.CompletedProcess([], 0, "private output", "private error")
        with (
            patch.object(installer.sys, "platform", "linux"),
            patch("os.geteuid", return_value=0),
            self.account(),
            patch.object(installer.subprocess, "run", return_value=result) as run,
        ):
            self.assertEqual(
                self.invoke(),
                {"journal_created": True, "policy_bound": True, "authority_issued": False},
            )
        args, kwargs = run.call_args
        self.assertEqual(
            args[0],
            [
                "/opt/aethron/venv/bin/python",
                "-I",
                "-B",
                "-m",
                "aethron_edge",
                "initialize-telemetry",
                "--config",
                "/opt/aethron/appliance.json",
                "--name",
                "flight",
                "--replay-floor",
                "123",
            ],
        )
        self.assertEqual(
            (kwargs["user"], kwargs["group"], kwargs["extra_groups"], kwargs["umask"]),
            (1234, 1234, [], 0o077),
        )
        self.assertEqual(kwargs["env"], {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"})
        self.assertEqual(kwargs["cwd"], "/")
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(kwargs["timeout"], 30)

    def test_wrong_host_nonroot_or_root_service_account_refused_before_execution(self):
        with patch.object(installer.subprocess, "run") as run:
            with patch.object(installer.sys, "platform", "darwin"), self.assertRaises(ValueError):
                self.invoke()
            with (
                patch.object(installer.sys, "platform", "linux"),
                patch("os.geteuid", return_value=1234),
                self.assertRaises(ValueError),
            ):
                self.invoke()
            with (
                patch.object(installer.sys, "platform", "linux"),
                patch("os.geteuid", return_value=0),
                patch("pwd.getpwnam", return_value=SimpleNamespace(pw_uid=0, pw_gid=0)),
                self.assertRaises(ValueError),
            ):
                self.invoke()
            run.assert_not_called()

    def test_missing_account_bad_arguments_and_failed_child_do_not_retry(self):
        with (
            patch.object(installer.sys, "platform", "linux"),
            patch("os.geteuid", return_value=0),
            self.account(),
            patch.object(installer.subprocess, "run") as run,
        ):
            for name, floor in (
                ("../flight", 123),
                ("flight", None),
                ("flight", True),
                ("flight", -1),
                ("flight", 2**48),
            ):
                with self.assertRaises(ValueError):
                    self.invoke(name, floor)
            run.assert_not_called()
            run.return_value = subprocess.CompletedProcess([], 2, "", "private details")
            with self.assertRaisesRegex(ValueError, "^service_telemetry_provisioning_failed$"):
                self.invoke()
            run.assert_called_once()
        with (
            patch.object(installer.sys, "platform", "linux"),
            patch("os.geteuid", return_value=0),
            patch("pwd.getpwnam", side_effect=KeyError("aethron")),
            self.assertRaises(ValueError),
        ):
            self.invoke()

    def test_timeout_does_not_retry_or_change_state(self):
        with (
            patch.object(installer.sys, "platform", "linux"),
            patch("os.geteuid", return_value=0),
            self.account(),
            patch.object(
                installer.subprocess, "run", side_effect=subprocess.TimeoutExpired("fixture", 30)
            ) as run,
        ):
            with self.assertRaisesRegex(ValueError, "^service_telemetry_provisioning_failed$"):
                self.invoke()
            run.assert_called_once()

    def test_cli_rejects_mixed_install_and_provisioning_arguments(self):
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                str(ROOT / "packaging/appliance/install.py"),
                "--initialize-telemetry",
                "flight",
                "--replay-floor",
                "123",
                "--root",
                "/",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("install arguments forbidden", result.stderr)

    def test_boot_unit_never_initializes_state_and_makes_it_private(self):
        service = (ROOT / "packaging/appliance/systemd/aethron.service").read_text()
        self.assertIn("StateDirectoryMode=0700", service)
        self.assertNotIn("initialize-telemetry", service)
        self.assertNotIn("ExecStartPre", service)
