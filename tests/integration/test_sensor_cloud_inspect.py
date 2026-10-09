"""Offline raw cloud inspection preserves ordinals and never publishes partial output."""

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
from pathlib import Path

import test_sensor_replay as legacy
from test_sensor_cloud_replay_v2 import packet


class CloudInspection(unittest.TestCase):
    def api(self):
        name = "aethron_edge.sensors.cloud_inspect"
        self.assertIsNotNone(importlib.util.find_spec(name), "cloud inspector missing")
        return __import__(name, fromlist=["inspect_recording"])

    def inspect(self, raw, indices=(0,), max_frames=1, **changes):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cloud.aeraw"
            path.write_bytes(raw)
            arguments = {
                "expected_sha256": hashlib.sha256(raw).hexdigest(),
                "indices": indices,
                "max_frames": max_frames,
            }
            arguments.update(changes)
            return api.inspect_recording(path, **arguments)

    def test_import_does_not_load_live_capture_or_geometry_runtime(self):
        self.api()
        import aethron_edge

        env = dict(os.environ, PYTHONPATH=str(Path(aethron_edge.__file__).parent.parent))
        command = [sys.executable] + (["-I"] if sys.flags.isolated else [])
        command += [
            "-c",
            "import json, sys; import aethron_edge.sensors.cloud_inspect; "
            "print(json.dumps([name for name in sys.modules if "
            "name.startswith(('aethron_edge.sources', 'aethron_edge.sensors.provider', "
            "'aethron_edge.sensors.registration', 'aethron_edge.sensors.rectification'))]))",
        ]
        result = subprocess.run(
            command, env=env, capture_output=True, text=True, timeout=30, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])

    def test_variable_empty_and_invalid_clouds_preserve_recorded_ordinals(self):
        raw = (
            packet(1, [(1, 2, 3), (float("nan"), 0, 0), (4, 5, 6)])
            + packet(2, [])
            + packet(3, [(7, 8, 9)], padding=4)
        )
        report = self.inspect(raw, indices=(2, 0, 1), max_frames=3)
        self.assertEqual(report["recording_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(report["indices"], [2, 0, 1])
        self.assertEqual(report["state"], "UNKNOWN")
        self.assertEqual(report["source_evidence"], "recorded")
        self.assertFalse(report["live_evidence"])
        self.assertFalse(report["registered"])
        frames = report["frames"]
        self.assertEqual([f["sample_count"] for f in frames], [3, 0, 1])
        self.assertEqual([f["invalid_sample_count"] for f in frames], [1, 0, 0])
        self.assertEqual(
            frames[0]["samples"],
            [
                {"xyz_m": [4, 5, 6], "radial_velocity_mps": None},
                {"xyz_m": [1, 2, 3], "radial_velocity_mps": None},
                None,
            ],
        )
        self.assertEqual(frames[1]["samples"], [None, None, None])
        self.assertEqual(frames[2]["samples"][1]["xyz_m"], [7, 8, 9])
        for i, frame in enumerate(frames, 1):
            header = frame["source_header"]
            self.assertEqual(header["acquisition_ns"], i * 1_000_000)
            self.assertEqual(header["uncertainty_ns"], 1000)
            self.assertEqual(header["clock_domain"], "recorded_monotonic")
            self.assertEqual(header["coordinate_frame"], "radar_front")
            self.assertEqual(header["calibration_sha256"], "a" * 64)

    def test_v1_big_endian_cloud_retains_signed_radial_velocity(self):
        seed = packet(1, [(0, 0, 0)], version=1)
        size = struct.unpack(">I", seed[:4])[0]
        header = json.loads(seed[4 : 4 + size])
        data = struct.pack(">4d", 1, 2, 3, -4) + b"padding!"
        header["layout"].update(
            is_bigendian=True,
            point_step=32,
            row_step=40,
            fields=[
                {"name": name, "offset": i * 8, "datatype": 8, "count": 1}
                for i, name in enumerate(("x", "y", "z", "radial_velocity"))
            ],
        )
        header["payload_sha256"] = hashlib.sha256(data).hexdigest()
        encoded = json.dumps(header).encode()
        report = self.inspect(struct.pack(">I", len(encoded)) + encoded + data)
        self.assertEqual(
            report["frames"][0]["samples"],
            [{"xyz_m": [1, 2, 3], "radial_velocity_mps": -4}],
        )

    def test_digest_corruption_trailing_data_and_images_reject(self):
        raw = packet(1, [(1, 2, 3)])
        for value in (b"", raw[:-1], raw[:-1] + b"X", raw + b"bad", legacy.SensorReplay().packet()):
            with self.subTest(size=len(value)), self.assertRaises(ValueError):
                self.inspect(value)
        for digest in ("0" * 64, "secret", None, True, "a" * 65):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                self.inspect(raw, expected_sha256=digest)

    def test_selection_and_frame_limits_are_strict_and_do_not_truncate(self):
        raw = packet(1, [])
        for indices in ((), (True,), (-1,), (4096,), (0, 0), tuple(range(65)), "0"):
            with self.subTest(indices=indices), self.assertRaises(ValueError):
                self.inspect(raw, indices=indices)
        for count in (0, 301, True, 1.0, None):
            with self.subTest(count=count), self.assertRaises(ValueError):
                self.inspect(raw, max_frames=count)
        with self.assertRaises(ValueError):
            self.inspect(raw + packet(2, []))
        with self.assertRaises(ValueError):
            self.inspect(raw + packet(2, [], acquisition_ns=30_001_000_001), max_frames=2)
        report = self.inspect(
            b"".join(packet(i, []) for i in range(300)), indices=tuple(range(64)), max_frames=300
        )
        self.assertEqual(len(report["frames"]), 300)
        self.assertEqual(report["frames"][-1]["samples"], [None] * 64)

    def test_regular_files_only_and_oversized_sparse_file_reject(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "too-large.aeraw"
            with path.open("wb") as stream:
                stream.truncate(64 * 1024 * 1024 + 1)
            for bad in (root, path, root / "absent"):
                with self.subTest(path=bad.name), self.assertRaises(ValueError):
                    api.inspect_recording(bad, expected_sha256="0" * 64, indices=(0,))
            if os.name == "posix":
                link = root / "link"
                link.symlink_to(path)
                fifo = root / "fifo"
                os.mkfifo(fifo)
                for bad in (link, fifo):
                    with self.subTest(path=bad.name), self.assertRaises(ValueError):
                        api.inspect_recording(bad, expected_sha256="0" * 64, indices=(0,))

    def test_bounded_reader_detects_growth_and_hashes_the_bytes_consumed(self):
        api = self.api()
        reader = api._DigestReader(io.BytesIO(b"abcdef"))
        self.assertEqual(reader.read(2), b"ab")
        self.assertEqual(reader.read(4), b"cdef")
        self.assertEqual(reader.digest.hexdigest(), hashlib.sha256(b"abcdef").hexdigest())
        # Boundary injection avoids allocating a 64 MiB test fixture.
        reader.total = 64 * 1024 * 1024
        reader.stream = io.BytesIO(b"x")
        with self.assertRaises(ValueError):
            reader.read(4)

    def test_cli_success_then_late_failure_has_no_partial_output_or_input_echo(self):
        self.api()
        import aethron_edge

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "secret-recording.aeraw"
            raw = packet(1, [(1, 2, 3)])
            path.write_bytes(raw)
            env = dict(os.environ, PYTHONPATH=str(Path(aethron_edge.__file__).parent.parent))
            command = [sys.executable]
            if sys.flags.isolated:
                command.append("-I")
            command += [
                "-m",
                "aethron_edge.sensors.cloud_inspect",
                "--recording",
                str(path),
                "--expected-recording-sha256",
                hashlib.sha256(raw).hexdigest(),
                "--index",
                "0",
                "--max-frames",
                "2",
            ]

            def run():
                return subprocess.run(
                    command,
                    cwd=root,
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=30,
                    check=False,
                )

            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout)["frames"][0]["samples"][0]["xyz_m"], [1, 2, 3]
            )
            path.write_bytes(raw + b"secret-corruption")
            result = run()
            self.assertEqual(
                (result.returncode, result.stdout, result.stderr),
                (2, "", "invalid_cloud_inspection\n"),
            )
            command += ["--unknown-option", "secret"]
            result = run()
            self.assertEqual(
                (result.returncode, result.stdout, result.stderr),
                (2, "", "invalid_cloud_inspection\n"),
            )
