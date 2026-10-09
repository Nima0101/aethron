"""Offline command uses recorded clocks and emits bounded selected counts only."""

import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import test_sensor_intensity_replay as fixtures


class IntensityInspection(unittest.TestCase):
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
