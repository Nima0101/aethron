"""Offline command uses recorded clocks and emits bounded selected counts only."""

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
