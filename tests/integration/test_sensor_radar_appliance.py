"""Original synthetic organized radar packets through recorded appliance admission."""

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import test_sensor_provider as provider_fixture
from aethron_edge.config import load_config
from aethron_edge.sensors.packets import CloudLayout, layout_digest
from aethron_edge.sensors.provider import GeometryProvider
from aethron_edge.sensors.provisioning import load_manifest, verified_recording
from aethron_edge.sensors.replay import read_frames
from aethron_edge.sensors.worker import replay_worker


def fixture(root, indices, *, bigendian=True, valid_for_ns=500_000_000):
    helper = provider_fixture.SensorProvider()
    helper.setUp()
    layout = CloudLayout(
        width=2,
        height=2,
        point_step=16,
        row_step=40,
        is_bigendian=bigendian,
        fields=[
            {"name": name, "offset": i * 4, "datatype": 7, "count": 1}
            for i, name in enumerate(("x", "y", "z", "radial_velocity"))
        ],
    )
    calibration = helper.config(
        modality="radar", source_camera=None, layout_sha256=layout_digest(layout)
    )
    payload = bytearray(80)
    endian = ">" if bigendian else "<"
    for index, values in enumerate(
        ((float("nan"), 0, 5, 0), (0, 0, 5, -2), (0.5, 0, 5, 3), (0, float("inf"), 5, 0))
    ):
        struct.pack_into(endian + "4f", payload, index // 2 * 40 + index % 2 * 16, *values)
    raw = bytearray()
    for sequence in range(2):
        header = {
            "version": 1,
            "source_id": calibration.source_id,
            "sequence": sequence,
            "acquisition_ns": 1_000_000_000 + sequence * 50_000_000,
            "clock_domain": "recorded_monotonic",
            "uncertainty_ns": 1_000_000,
            "coordinate_frame": calibration.rig.source_frame,
            "modality": "radar",
            "calibration_sha256": calibration.digest,
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "layout": layout.model_dump(),
        }
        encoded = json.dumps(header).encode()
        raw.extend(struct.pack(">I", len(encoded)) + encoded + payload)
    source = root / "radar.aeraw"
    source.write_bytes(raw)
    manifest = root / "sensor.json"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "mode": "recorded",
                "calibration": calibration.model_dump(),
                "indices": indices,
                "valid_for_ns": valid_for_ns,
                "loop": False,
                "recording_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    )
    config = root / "appliance.json"
    config.write_text(
        json.dumps(
            {
                "version": 1,
                "status_file": "status.json",
                "profiles": [
                    {
                        "name": "radar",
                        "driver": "sensor-replay",
                        "address": source.name,
                        "sensor_manifest": manifest.name,
                    }
                ],
            }
        )
    )
    return config, manifest, source, calibration


class RadarReplay(unittest.TestCase):
    def test_invalid_cloud_samples_do_not_shift_configured_selection(self):
        for endian in (True, False):
            for indices, expected in (
                ([0], []),
                ([1], [(0.5, 0, 5)]),
                ([2], [(1, 0, 5)]),
                ([3], []),
            ):
                with (
                    self.subTest(endian=endian, indices=indices),
                    tempfile.TemporaryDirectory() as tmp,
                ):
                    _, path, source, calibration = fixture(Path(tmp), indices, bigendian=endian)
                    with source.open("rb") as stream:
                        frame = next(read_frames(stream))
                    provider = GeometryProvider(
                        calibration,
                        mode="recorded",
                        clock_id="recording",
                        valid_for_ns=500_000_000,
                        clock=lambda: 1_001_000_000,
                    )
                    result = provider.recorded(frame, indices, mount_id=calibration.rig.mount_id)
                    self.assertEqual([p.camera_xyz_m for p in result.points], expected)
                    self.assertEqual(result.invalid_samples, 0 if expected else 1)
                    self.assertEqual(result.source_evidence, "recorded")
                    self.assertFalse(result.live_evidence)
                    with verified_recording(source, load_manifest(path)) as stream:
                        self.assertEqual(len(list(read_frames(stream))), 2)
                    provider.close()

    def test_worker_invalid_selection_never_reports_available_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, _, _, _ = fixture(Path(tmp), [0])
            stop = threading.Event()
            messages = []

            def send(message):
                messages.append(message)
                stop.set()

            with patch("aethron_edge.sensors.worker.time.monotonic_ns", return_value=1_000_000_000):
                replay_worker(load_config(config).profiles[0], send, stop)
            self.assertEqual(len(messages), 1)
            self.assertIsNone(messages[0]["data"])
            self.assertEqual(messages[0]["sensor_batches"], 1)
            self.assertEqual(messages[0]["sensor_expires_ns"], 0)

    def test_signed_cli_replay_ends_unknown_and_rejects_tampering(self):
        from aethron_edge.cli import main

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        private, public = base / "test-only.pem", base / "test-only.pub"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)],
            check=True,
            capture_output=True,
        )
        root = base / "radar"
        root.mkdir()
        config, manifest, source, _ = fixture(root, [0, 1, 2, 3])
        settings = json.loads(config.read_text())
        settings.update(
            integrity_bundle=str(root),
            trust_root=str(public),
            status_file=str(base / "status.json"),
        )
        config.write_text(json.dumps(settings))
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "version": 1,
                    "config_version": 1,
                    "files": {
                        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (config, manifest, source)
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
                str(private),
                "-in",
                str(root / "manifest.json"),
                "-out",
                str(root / "manifest.sig"),
            ],
            check=True,
            capture_output=True,
        )
        states = []

        def observe(settings, *, supervisor):
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                with supervisor.lock:
                    status = supervisor.status(time.monotonic_ns())
                    row = status["sensors"]["radar"]
                if row["state"] == "ended":
                    break
                time.sleep(0.02)
            else:
                self.fail("signed radar replay did not finish")
            self.assertEqual(row["batches"], 2)
            self.assertFalse(row["available"])
            self.assertFalse(row["qualified"])
            self.assertEqual(row["source_evidence"], "recorded")
            self.assertEqual(supervisor.snapshot("radar")["state"], "UNKNOWN")
            self.assertEqual(supervisor.snapshot("radar")["tracks"], [])
            self.assertEqual(status["restarts"], 0)
            self.assertNotIn("camera_xyz", json.dumps(status))
            states.append(row)

        with patch.object(sys, "argv", ["aethron-edge", "run", "--config", str(config)]):
            with patch("aethron_edge.service.app.serve", side_effect=observe):
                main()
            self.assertEqual(len(states), 1)
            for path in (manifest, source):
                original = path.read_bytes()
                path.write_bytes(original + b"x")
                with patch("aethron_edge.runtime.entrypoint.run") as run:
                    with self.assertRaises(SystemExit) as rejected:
                        main()
                    self.assertEqual(rejected.exception.code, 2)
                    run.assert_not_called()
                path.write_bytes(original)

    def test_calibration_expiry_rejects_whole_recording_before_worker_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, manifest, source, _ = fixture(Path(tmp), [1, 2], valid_for_ns=10_000_000)
            with self.assertRaises(ValueError):
                with verified_recording(source, load_manifest(manifest)):
                    self.fail("expired recording admitted")
            messages = []
            replay_worker(load_config(config).profiles[0], messages.append, threading.Event())
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["sensor_state"], "fault")
            self.assertEqual(messages[0]["sensor_batches"], 0)
            self.assertEqual(messages[0]["sensor_expires_ns"], 0)
