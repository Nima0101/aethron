"""A failed new ROS check must never coexist with a stale successful report."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def runner():
    spec = importlib.util.spec_from_file_location("ros_check", ROOT / "scripts/edge_ros2_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RosCheckOutput(unittest.TestCase):
    def test_existing_evidence_is_refused_before_copy_or_container_execution(self):
        module = runner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "prior"
            out.mkdir()
            result = out / "result.json"
            result.write_text('{"installed_ros_dds":true}\n')
            before = result.read_bytes()
            # Inputs intentionally absent. Output refusal must precede their use.
            with patch.object(
                module.subprocess, "run", side_effect=AssertionError("container_started")
            ):
                with self.assertRaises(FileExistsError):
                    module.run(root / "wheels", root / "dependencies", out)
            self.assertEqual(result.read_bytes(), before)
            self.assertEqual(list(out.iterdir()), [result])

    def test_symlink_to_another_runs_directory_is_refused(self):
        module = runner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prior = root / "prior"
            prior.mkdir()
            out = root / "alias"
            out.symlink_to(prior, target_is_directory=True)
            with patch.object(
                module.subprocess, "run", side_effect=AssertionError("container_started")
            ):
                with self.assertRaises(FileExistsError):
                    module.run(root / "wheels", root / "dependencies", out)
            self.assertEqual(list(prior.iterdir()), [])

    def test_failed_fresh_run_retains_log_without_success_report(self):
        from subprocess import CompletedProcess

        module = runner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "fresh"

            def failed(command, **kwargs):
                if command[:2] == ["docker", "run"]:
                    kwargs["stdout"].write("fixture container failed\n")
                    return CompletedProcess(command, 1)
                return CompletedProcess(command, 0)

            with patch.object(module.subprocess, "run", side_effect=failed):
                with self.assertRaisesRegex(SystemExit, "ROS DDS check failed"):
                    module.run(root / "wheels", root / "dependencies", out)
            self.assertEqual((out / "dds.log").read_text(), "fixture container failed\n")
            self.assertFalse((out / "result.json").exists())
            self.assertTrue((out / "bundle/wheels.json").is_file())

    def test_timing_diagnostics_require_explicit_opt_in(self):
        from subprocess import CompletedProcess

        module = runner()
        for enabled in (False, True):
            with self.subTest(diagnostics=enabled), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                commands = []

                def failed(command, commands=commands, **kwargs):
                    commands.append(command)
                    return CompletedProcess(command, 1)

                with patch.object(module.subprocess, "run", side_effect=failed):
                    with self.assertRaises(SystemExit):
                        options = {"diagnostics": True} if enabled else {}
                        module.run(root / "wheels", root / "dependencies", root / "out", **options)
                self.assertEqual("AETHRON_ROS_TEST_DIAGNOSTICS=1" in commands[0], enabled)
                self.assertIn("--network", commands[0])
                self.assertIn("none", commands[0])
                self.assertTrue((root / "out/bundle/tests/ros_timing_probe.py").is_file())
