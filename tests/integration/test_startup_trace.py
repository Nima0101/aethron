"""Startup diagnostics are bounded, opt-in and cannot disclose caller material."""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(enabled):
    spec = importlib.util.spec_from_file_location(
        "trace_test", ROOT / "integrations/edge/aethron_edge/_startup_trace.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, {"AETHRON_STARTUP_TRACE": enabled}):
        spec.loader.exec_module(module)
    return module


class StartupTraceTests(unittest.TestCase):
    def test_disabled_trace_does_not_write_or_read_clock(self):
        for value in ("", "0", "true"):
            trace = load(value)
            with (
                patch.object(trace.os, "write") as write,
                patch.object(trace.time, "monotonic_ns") as clock,
            ):
                trace.mark("process_entry")
                write.assert_not_called()
                clock.assert_not_called()

    def test_only_fixed_unique_stages_are_emitted(self):
        trace = load("1")
        with (
            patch.object(trace.os, "write") as write,
            patch.object(trace.time, "monotonic_ns", return_value=123456789),
        ):
            for stage in (
                "secret path /private",
                "process_entry",
                "process_entry",
                "runtime_boot_done",
            ):
                trace.mark(stage)
        self.assertEqual(
            [x.args for x in write.call_args_list],
            [
                (2, b"AETHRON_STARTUP process_entry 123456789\n"),
                (2, b"AETHRON_STARTUP runtime_boot_done 123456789\n"),
            ],
        )

    def test_failed_output_is_not_retried_and_does_not_break_startup(self):
        trace = load("1")
        with patch.object(trace.os, "write", side_effect=OSError("private details")) as write:
            trace.mark("process_entry")
            trace.mark("process_entry")
        write.assert_called_once()

    def test_guest_trace_is_explicit_and_covers_both_service_startups(self):
        spec = importlib.util.spec_from_file_location(
            "prepare", ROOT / "packaging/appliance/image/prepare.py"
        )
        prepare = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prepare)
        for enabled in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                context = Path(tmp)
                prepare.stage_inputs(context, ros=True, startup_trace=enabled)
                for unit in ("aethron.service", "ros-runtime.service"):
                    text = (context / unit).read_text()
                    self.assertEqual("Environment=AETHRON_STARTUP_TRACE=1" in text, enabled)
                    if enabled:
                        self.assertIn("StandardError=journal+console", text)

    def test_image_cli_forwards_explicit_diagnostic_flag(self):
        spec = importlib.util.spec_from_file_location(
            "prepare", ROOT / "packaging/appliance/image/prepare.py"
        )
        prepare = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prepare)
        for flag in ([], ["--startup-trace"]):
            with (
                patch.object(
                    sys,
                    "argv",
                    ["prepare", "--out", "out", "--wheels", "wheels", "--test-key", "key"] + flag,
                ),
                patch.object(prepare, "prepare") as build,
            ):
                prepare.main()
            self.assertEqual(build.call_args.kwargs["startup_trace"], bool(flag))

    def test_installed_cli_reports_failed_config_stage_without_path_or_completion(self):
        env = dict(os.environ, AETHRON_STARTUP_TRACE="1")
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-m",
                "aethron_edge",
                "run",
                "--config",
                "/nonexistent/private-config-secret.json",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("private-config-secret", result.stderr)
        stages = [
            line.split()[1]
            for line in result.stderr.splitlines()
            if line.startswith("AETHRON_STARTUP ")
        ]
        self.assertEqual(
            stages, ["process_entry", "cli_ready", "config_import_start", "config_import_done"]
        )
        self.assertIn("startup_failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
