"""Offline command retains source metadata alongside bounded selected counts."""

import hashlib
import importlib.util
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import test_sensor_intensity_replay as fixtures


class IntensityInspectionDiagnostics(unittest.TestCase):
    def test_help_uses_public_module_name_not_invocation_name(self):
        from aethron_edge.sensors.intensity_inspect import main

        output, errors = io.StringIO(), io.StringIO()
        with (
            patch.object(sys, "argv", ["/private/private-invocation-sentinel", "--help"]),
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            with self.assertRaises(SystemExit) as result:
                main()
        self.assertEqual(result.exception.code, 0)
        self.assertEqual(errors.getvalue(), "")
        self.assertNotIn("private-invocation-sentinel", output.getvalue())
        self.assertIn("aethron_edge.sensors.intensity_inspect", output.getvalue())
        self.assertIn("--recording", output.getvalue())
        self.assertIn("--pixel", output.getvalue())

    def test_argument_errors_do_not_echo_private_values(self):
        from aethron_edge.sensors.intensity_inspect import main

        valid = [
            "--recording",
            "/private/recording-sentinel",
            "--calibration",
            "/private/calibration-sentinel",
            "--expected-calibration-sha256",
            "0" * 64,
            "--pixel",
            "0",
            "0",
        ]
        for args in (
            [],
            [*valid, "--private-option-sentinel"],
            [*valid, "--pixel", "private-pixel-sentinel", "0"],
            [*valid, "--max-frames", "private-count-sentinel"],
        ):
            with self.subTest(args=args):
                output, errors = io.StringIO(), io.StringIO()
                with (
                    patch.object(sys, "argv", ["private-invocation-sentinel", *args]),
                    redirect_stdout(output),
                    redirect_stderr(errors),
                ):
                    with self.assertRaises(SystemExit) as result:
                        main()
                self.assertEqual(result.exception.code, 2)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(errors.getvalue(), "invalid_intensity_inspection\n")

    def test_file_error_does_not_echo_private_exception_or_path(self):
        from aethron_edge.sensors import intensity_inspect as api

        args = [
            "private-invocation-sentinel",
            "--recording",
            "/private/recording-sentinel",
            "--calibration",
            "/private/calibration-sentinel",
            "--expected-calibration-sha256",
            "0" * 64,
            "--pixel",
            "0",
            "0",
        ]
        original = OSError("private-error-sentinel")
        output, errors = io.StringIO(), io.StringIO()
        with (
            patch.object(sys, "argv", args),
            patch.object(api, "regular_file", side_effect=original) as read,
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            with self.assertRaises(SystemExit) as result:
                api.main()
        read.assert_called_once_with(Path("/private/calibration-sentinel"), 65536)
        self.assertEqual(result.exception.code, 2)
        self.assertIs(result.exception.__context__, original)
        self.assertIn("private-error-sentinel", str(result.exception.__context__))
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(errors.getvalue(), "invalid_intensity_inspection\n")

    def test_unhandled_faults_propagate_without_fixed_diagnostic(self):
        from aethron_edge.sensors import intensity_inspect as api

        args = [
            "inspection-test",
            "--recording",
            "unused-recording",
            "--calibration",
            "unused-calibration",
            "--expected-calibration-sha256",
            "0" * 64,
            "--pixel",
            "0",
            "0",
        ]
        for error_type in (RuntimeError, MemoryError, KeyboardInterrupt, SystemExit):
            with self.subTest(error=error_type.__name__):
                original = error_type("injected-unhandled-fault")
                output, errors = io.StringIO(), io.StringIO()
                with (
                    patch.object(sys, "argv", args),
                    patch.object(api, "regular_file", side_effect=original) as read,
                    redirect_stdout(output),
                    redirect_stderr(errors),
                ):
                    with self.assertRaises(error_type) as raised:
                        api.main()
                read.assert_called_once_with(Path("unused-calibration"), 65536)
                self.assertIs(raised.exception, original)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(errors.getvalue(), "")


class IntensityInspection(unittest.TestCase):
    def test_report_retains_metadata_but_late_rejection_discloses_no_report(self):
        from aethron_edge.sensors.intensity_inspect import main

        _, calibration, frame = fixtures.SensorIntensityReplay().fixture()
        raw = frame.header.model_dump_json().encode()
        recording_bytes = struct.pack(">I", len(raw)) + raw + frame.payload.data
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording = root / "private-recording-name.bin"
            document = root / "private-calibration-name.json"
            recording.write_bytes(recording_bytes)
            document.write_text(calibration.model_dump_json())
            args = [
                "intensity_inspect",
                "--recording",
                str(recording),
                "--calibration",
                str(document),
                "--expected-calibration-sha256",
                calibration.digest,
                "--pixel",
                "0",
                "0",
            ]
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(sys, "argv", args), redirect_stdout(output), redirect_stderr(errors):
                main()
            report = json.loads(output.getvalue())
            self.assertEqual(errors.getvalue(), "")
            self.assertEqual(report["frames"][0]["counts"], [0])
            self.assertEqual(
                report["frames"][0]["source_header"], json.loads(frame.header.model_dump_json())
            )
            self.assertFalse(report["live_evidence"])
            self.assertNotIn(str(root), output.getvalue())
            # A complete valid first frame must not escape when later parsing fails.
            recording.write_bytes(recording_bytes + b"bad")
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(sys, "argv", args), redirect_stdout(output), redirect_stderr(errors):
                with self.assertRaises(SystemExit) as exit_result:
                    main()
            self.assertEqual(exit_result.exception.code, 2)
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(errors.getvalue(), "invalid_intensity_inspection\n")

    def test_offline_inspection_does_not_load_live_provider_or_provisioning(self):
        import aethron_edge

        env = dict(os.environ, PYTHONPATH=str(Path(aethron_edge.__file__).parent.parent))
        command = [
            sys.executable,
            *(["-I"] if sys.flags.isolated else []),
            "-c",
            "import json, sys; import aethron_edge.sensors.intensity_inspect; "
            "print(json.dumps([n for n in sys.modules if n.startswith("
            "('aethron_edge.sensors.provider', 'aethron_edge.sensors.provisioning', "
            "'aethron_edge.runtime'))]))",
        ]
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                command,
                cwd=directory,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])

    def test_recording_pin_binds_complete_file_before_any_output(self):
        import aethron_edge

        _, calibration, frame = fixtures.SensorIntensityReplay().fixture(encoding="mono16")

        def record(sequence):
            header = (
                frame.header.model_copy(update={"sequence": sequence}).model_dump_json().encode()
            )
            return struct.pack(">I", len(header)) + header + frame.payload.data

        first, second = record(19), record(20)
        whole = first + second
        pin = hashlib.sha256(whole).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording, document = root / "raw.bin", root / "calibration.json"
            recording.write_bytes(whole)
            document.write_text(calibration.model_dump_json())
            command = [
                sys.executable,
                *(["-I"] if sys.flags.isolated else []),
                "-m",
                "aethron_edge.sensors.intensity_inspect",
                "--recording",
                str(recording),
                "--calibration",
                str(document),
                "--expected-calibration-sha256",
                calibration.digest,
                "--pixel",
                "1",
                "0",
                "--max-frames",
                "2",
            ]
            env = dict(os.environ, PYTHONPATH=str(Path(aethron_edge.__file__).parent.parent))

            def run(expected=None):
                extra = [] if expected is None else ["--expected-recording-sha256", expected]
                return subprocess.run(
                    command + extra,
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )

            legacy = run()
            self.assertEqual(legacy.returncode, 0, legacy.stderr)
            pinned = run(pin)
            self.assertEqual(pinned.returncode, 0, pinned.stderr)
            self.assertEqual(pinned.stdout, legacy.stdout)
            self.assertEqual(
                [f["counts"] for f in json.loads(pinned.stdout)["frames"]], [[256], [256]]
            )
            for expected in (
                "0" * 64,
                pin.upper(),
                "private-sentinel",
                hashlib.sha256(first).hexdigest(),
            ):
                with self.subTest(expected=expected):
                    bad = run(expected)
                    self.assertEqual(
                        (bad.returncode, bad.stdout, bad.stderr),
                        (2, "", "invalid_intensity_inspection\n"),
                    )
            # Each prefix packet is valid; packet checksums cannot detect this substitution.
            recording.write_bytes(first)
            self.assertEqual(run().returncode, 0)
            missing = run(pin)
            self.assertEqual(
                (missing.returncode, missing.stdout, missing.stderr),
                (2, "", "invalid_intensity_inspection\n"),
            )
            recording.write_bytes(whole + b"bad")
            malformed = run(hashlib.sha256(whole + b"bad").hexdigest())
            self.assertEqual(
                (malformed.returncode, malformed.stdout, malformed.stderr),
                (2, "", "invalid_intensity_inspection\n"),
            )

    def test_cli_success_and_fail_closed_limits(self):
        name = "aethron_edge.sensors.intensity_inspect"
        self.assertIsNotNone(importlib.util.find_spec(name), "inspection command missing")
        _, calibration, frame = fixtures.SensorIntensityReplay().fixture(encoding="mono16")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recording, document = root / "raw.bin", root / "calibration.json"
            document.write_text(calibration.model_dump_json())

            def record(sequence):
                header = (
                    frame.header.model_copy(update={"sequence": sequence})
                    .model_dump_json()
                    .encode()
                )
                return struct.pack(">I", len(header)) + header + frame.payload.data

            recording.write_bytes(record(19))
            command = [
                sys.executable,
                "-m",
                name,
                "--recording",
                str(recording),
                "--calibration",
                str(document),
                "--expected-calibration-sha256",
                calibration.digest,
                "--pixel",
                "0",
                "0",
                "--pixel",
                "1",
                "0",
                "--pixel",
                "3",
                "0",
            ]
            env = dict(os.environ)
            # Bind the subprocess to the same source/installed module selected by this test.
            import aethron_edge

            env["PYTHONPATH"] = str(Path(aethron_edge.__file__).parent.parent)

            def run(extra=()):
                return subprocess.run(
                    command + list(extra),
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )

            good = run()
            self.assertEqual(good.returncode, 0, good.stderr)
            output = json.loads(good.stdout)
            self.assertFalse(output["live_evidence"])
            self.assertEqual(
                output["frames"][0]["source_header"], json.loads(frame.header.model_dump_json())
            )
            self.assertEqual(output["frames"][0]["counts"], [0, 256, None])
            for extra in (
                ("--max-frames", "0"),
                ("--max-frames", "301"),
                ("--pixel", "4", "0"),
                ("--expected-calibration-sha256", "bad"),
                tuple(["--pixel", "0", "0"] * 65),
            ):
                with self.subTest(extra=extra):
                    bad = run(extra)
                    self.assertEqual(
                        (bad.returncode, bad.stdout, bad.stderr),
                        (2, "", "invalid_intensity_inspection\n"),
                    )
            recording.write_bytes(record(19) + record(20))
            self.assertEqual(run().returncode, 2)
            self.assertEqual(len(json.loads(run(("--max-frames", "2")).stdout)["frames"]), 2)
            recording.write_bytes(record(19) + b"bad")
            bad = run(("--max-frames", "2"))
            self.assertEqual((bad.returncode, bad.stdout), (2, ""))
            document.write_text('{"version":1,"version":1}')
            self.assertEqual(run().returncode, 2)
