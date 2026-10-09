"""Provisioned raw replay must run without viewers and never become live evidence."""

import hashlib
import importlib.util
import json
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import test_sensor_provider as provider_fixture
from aethron_edge.config import Profile, load_config
from aethron_edge.runtime.supervisor import ApplianceSupervisor
from aethron_edge.runtime.updates import verify_configuration


def fixture(root, *, loop=True, count=6, interval_ns=50_000_000):
    helper = provider_fixture.SensorProvider()
    helper.setUp()
    calibration = helper.config()
    raw = bytearray()
    for index in range(count):
        frame = helper.frame(calibration, stamp=1_000_000_000 + index * interval_ns, sequence=index)
        header = frame.header.model_dump(mode="json")
        encoded = json.dumps(header).encode()
        raw.extend(struct.pack(">I", len(encoded)) + encoded + frame.payload.data)
    source = root / "depth.aeraw"
    source.write_bytes(raw)
    manifest = {
        "version": 1,
        "mode": "recorded",
        "calibration": calibration.model_dump(mode="json"),
        "indices": [[1, 1]],
        "valid_for_ns": 30_000_000_000,
        "loop": loop,
        "recording_sha256": hashlib.sha256(raw).hexdigest(),
    }
    path = root / "sensor.json"
    path.write_text(json.dumps(manifest))
    config = root / "appliance.json"
    config.write_text(
        json.dumps(
            {
                "version": 1,
                "status_file": "status.json",
                "profiles": [
                    {
                        "name": "depth",
                        "driver": "sensor-replay",
                        "address": source.name,
                        "sensor_manifest": path.name,
                    }
                ],
            }
        )
    )
    return config, path, source, manifest


class SensorAppliance(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("aethron_edge.sensors.provisioning"))
        from aethron_edge.sensors import provisioning

        return provisioning

    def test_closed_manifest_and_profile_binding(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path, manifest_path, source, manifest = fixture(root)
            config = load_config(config_path)
            profile = config.profiles[0]
            self.assertEqual(profile.address, str(source.resolve()))
            self.assertEqual(profile.sensor_manifest, str(manifest_path.resolve()))
            loaded = api.load_manifest(manifest_path)
            self.assertEqual(loaded.indices, ((1, 1),))
            for change in (
                {"version": True},
                {"mode": "live"},
                {"valid_for_ns": True},
                {"valid_for_ns": 600_000_000_001},
                {"indices": [[1, 1]] * 65},
                {"indices": [[1, 1], [1, 1]]},
                {"indices": [[True, 1]]},
                {"indices": [[3, 1]]},
                {"indices": [0]},
                {"loop": 1},
                {"clock_offset_ns": 0},
            ):
                with self.subTest(change=change):
                    manifest_path.write_text(json.dumps({**manifest, **change}))
                    with self.assertRaisesRegex(ValueError, "invalid_sensor_manifest"):
                        api.load_manifest(manifest_path)
            for raw in (b'{"version":1,"version":1}', b"[" * 2000, b" " * 65537):
                manifest_path.write_bytes(raw)
                with self.assertRaisesRegex(ValueError, "invalid_sensor_manifest"):
                    api.load_manifest(manifest_path)
            for change in (
                {"sensor_manifest": None},
                {"model": "anything.onnx"},
                {"driver": "replay"},
            ):
                with self.subTest(profile=change), self.assertRaises(ValueError):
                    Profile.model_validate({**profile.model_dump(), **change})

    def test_provisioning_cannot_resolve_away_source_symlink(self):
        self.api()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path, manifest, source, _ = fixture(root)
            alias = root / "alias"
            alias.symlink_to(source)
            config = json.loads(config_path.read_text())
            config["profiles"][0]["address"] = alias.name
            config_path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                load_config(config_path)

    def test_manifest_and_recording_must_both_be_signed_inputs(self):
        self.api()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path, manifest_path, source, _ = fixture(root)
            config = load_config(config_path)
            config.integrity_bundle = str(root)
            config.trust_root = str(root / "trust.pub")
            names = [config_path.name, manifest_path.name, source.name]
            for omitted in (manifest_path.name, source.name, None):
                signed = {"files": {name: "a" * 64 for name in names if name != omitted}}
                with patch("aethron_edge.runtime.updates.verify_bundle", return_value=signed):
                    if omitted is None:
                        self.assertEqual(verify_configuration(config, config_path), signed)
                    else:
                        with self.assertRaisesRegex(ValueError, "unsigned_configuration_input"):
                            verify_configuration(config, config_path)

    def test_recording_validation_is_bounded_and_checks_whole_input(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, manifest_path, source, _ = fixture(root)
            manifest = api.load_manifest(manifest_path)
            api.validate_recording(source, manifest)
            original = source.read_bytes()
            for data in (original[:-1], original + b"x", b"", original[:-1] + b"x"):
                source.write_bytes(data)
                with self.assertRaises(ValueError):
                    api.validate_recording(source, manifest)
            source.write_bytes(original)
            alias = root / "alias"
            alias.symlink_to(source)
            with self.assertRaises(ValueError):
                api.validate_recording(alias, manifest)
            # Valid digest still cannot admit >300 frames or a >30-second span.
            _, manifest_path, source, _ = fixture(root, count=301)
            with self.assertRaises(ValueError):
                api.validate_recording(source, api.load_manifest(manifest_path))
            with source.open("wb") as stream:
                stream.truncate(64 * 1024 * 1024 + 1)
            with self.assertRaises(ValueError):
                api.validate_recording(source, manifest)

    def test_long_recorded_gap_sends_heartbeats_and_can_be_cancelled(self):
        self.api()
        from aethron_edge.sensors.worker import replay_worker

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path, _, _, _ = fixture(root, count=2, interval_ns=11_000_000_000)
            now = [1_000_000_000]
            emitted = []

            class Stop:
                def is_set(self):
                    return now[0] >= 2_000_000_000

                def wait(self, seconds):
                    now[0] += round(seconds * 1e9)
                    return self.is_set()

            stop = Stop()
            with patch("aethron_edge.sensors.worker.time.monotonic_ns", side_effect=lambda: now[0]):
                replay_worker(load_config(config_path).profiles[0], emitted.append, stop)
            self.assertLessEqual(now[0], 2_100_000_000)
            self.assertGreaterEqual(len(emitted), 5)
            self.assertTrue(all(m["data"] is None for m in emitted))
            self.assertTrue(all(m["sensor_batches"] == 1 for m in emitted))

    def test_raw_processing_reports_measured_duration(self):
        import threading

        from aethron_edge.sensors.provider import GeometryProvider
        from aethron_edge.sensors.worker import replay_worker

        # This is duration arithmetic/admission, not a host scheduling benchmark.
        # A real sleep can overrun AGE_NS and correctly withdraw the geometry.
        def check(duration_ns, expected):
            with tempfile.TemporaryDirectory() as directory:
                config_path, _, _, _ = fixture(Path(directory))
                stop = threading.Event()
                messages = []
                now = [1_000_000_000]
                original = GeometryProvider.recorded

                def measured(self, *args, **kwargs):
                    now[0] += duration_ns
                    return original(self, *args, **kwargs)

                def send(message):
                    messages.append(message)
                    stop.set()

                with patch(
                    "aethron_edge.sensors.worker.time.monotonic_ns", side_effect=lambda: now[0]
                ):
                    with patch.object(GeometryProvider, "recorded", measured):
                        replay_worker(load_config(config_path).profiles[0], send, stop)
                self.assertEqual(len(messages), 1)
                self.assertEqual(messages[0]["sensor_state"], expected)
                self.assertEqual(messages[0]["latency_ms"], duration_ns / 1e6)
                self.assertIsNone(messages[0]["data"])
                if expected == "fault":
                    self.assertEqual(messages[0]["sensor_expires_ns"], 0)
                    self.assertEqual(messages[0]["sensor_batches"], 0)

        for duration_ns, expected in ((2_000_000, "processing"), (100_000_000, "fault")):
            with self.subTest(duration_ns=duration_ns):
                check(duration_ns, expected)

    def wait_for(self, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        self.fail("supervised sensor condition was not reached")

    def test_zero_viewers_loss_crash_recovery_and_no_semantic_promotion(self):
        self.api()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path, _, source, _ = fixture(root)
            runtime = ApplianceSupervisor()
            runtime.boot(load_config(config_path))
            try:

                def state():
                    with runtime.lock:
                        return runtime.status(time.monotonic_ns())["sensors"]["depth"]

                self.wait_for(lambda: state()["batches"] >= 3)
                first = state()["batches"]
                self.assertEqual(state()["source_evidence"], "recorded")
                self.assertFalse(state()["qualified"])
                self.assertEqual(runtime.snapshot("depth")["state"], "UNKNOWN")
                self.assertEqual(runtime.snapshot("depth")["tracks"], [])
                self.assertEqual(runtime.pipelines["depth"].inferences, 0)
                # Parent monotonic expiry must work even if the producer is frozen.
                with runtime.lock:
                    p = runtime.pipelines["depth"]
                    self.assertFalse(
                        p.sensor_status(time.monotonic_ns() + 200_000_000)["available"]
                    )
                    original_pid = p.process.pid
                    p.process.terminate()
                self.wait_for(lambda: state()["batches"] > first + 3)
                self.assertNotEqual(runtime.pipelines["depth"].process.pid, original_pid)
                # Unplug simulation: missing local source withdraws raw availability.
                source.unlink()
                self.wait_for(lambda: not state()["available"])
                self.wait_for(lambda: runtime.pipelines["depth"].reason == "source_lost")
                self.assertEqual(runtime.snapshot("depth")["state"], "UNKNOWN")
                serialized = json.dumps(runtime.status(time.monotonic_ns()))
                self.assertNotIn("camera_xyz", serialized)
                self.assertNotIn("calibration", serialized)
                self.assertLess(len(serialized), 4096)
            finally:
                runtime.shutdown()
            self.assertTrue(all(p.process is None for p in runtime.pipelines.values()))

    def test_end_of_recording_is_idle_not_a_restart_loop(self):
        self.api()
        with tempfile.TemporaryDirectory() as directory:
            config_path, _, _, _ = fixture(Path(directory), loop=False)
            runtime = ApplianceSupervisor()
            runtime.boot(load_config(config_path))
            try:
                self.wait_for(
                    lambda: (
                        runtime.pipelines["depth"].sensor_status(time.monotonic_ns())["state"]
                        == "ended"
                    )
                )
                state = runtime.status(time.monotonic_ns())
                self.assertEqual(state["sensors"]["depth"]["batches"], 6)
                self.assertFalse(state["sensors"]["depth"]["available"])
                self.assertEqual(state["restarts"], 0)
                self.assertEqual(runtime.snapshot("depth")["state"], "UNKNOWN")
            finally:
                runtime.shutdown()
