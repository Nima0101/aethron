"""ROS appliance configuration/boot authority; real DDS runs in the pinned ROS lane."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import test_sensor_ros_authority as authority_fixture
from aethron_edge.config import Profile, load_config
from aethron_edge.pipeline import RuntimePipeline
from aethron_edge.runtime.updates import verify_configuration


def fixture(root, valid_for_ns=30_000_000_000, **changes):
    helper = authority_fixture.RosAuthority()
    helper.setUp()
    manifest = helper.manifest(valid_for_ns=valid_for_ns, **changes)
    (root / "sensor.json").write_text(manifest.model_dump_json())
    config = root / "appliance.json"
    config.write_text(
        json.dumps(
            {
                "version": 1,
                "status_file": "status.json",
                "profiles": [
                    {
                        "name": "depth",
                        "driver": "sensor-ros",
                        "address": manifest.topic,
                        "sensor_manifest": "sensor.json",
                    }
                ],
            }
        )
    )
    return config, manifest


def passive_worker(profile, channel, stop, group, decoder_lock, descendant, grant, control):
    from aethron_edge.process_tree import own_descendants

    own_descendants(group)
    while not stop.is_set():
        time.sleep(0.01)


class RosAppliance(unittest.TestCase):
    def test_observed_clock_shift_latches_fault_and_reaps_worker_without_restart(self):
        from aethron_edge.runtime.supervisor import ApplianceSupervisor

        with tempfile.TemporaryDirectory() as tmp:
            path, _ = fixture(Path(tmp))
            runtime = ApplianceSupervisor()
            with patch(
                "aethron_edge.runtime.supervisor.RuntimePipeline",
                side_effect=lambda profile, **kw: RuntimePipeline(
                    profile, worker=passive_worker, **kw
                ),
            ):
                try:
                    runtime.boot(load_config(path))
                    with runtime.lock:
                        pipeline = runtime.pipelines["depth"]
                        grant = pipeline.ros_grant
                        # Measured in the pinned installed ROS probe: offset changed
                        # 6.606 ms, well above this fixture's unchanged 1 ms budget.
                        pipeline.ros_guard.realtime = lambda: time.time_ns() + 6_605_682
                        status = runtime.tick(time.monotonic_ns())
                        self.assertEqual(status["state"], "fault")
                        self.assertIn("depth", runtime.faults)
                    deadline = time.monotonic() + 5
                    while pipeline.process is not None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertIsNone(pipeline.process)
                    with runtime.lock:
                        pipeline.ros_guard.realtime = time.time_ns
                        status = runtime.tick(time.monotonic_ns())
                        self.assertIs(runtime.pipelines["depth"], pipeline)
                        self.assertEqual(pipeline.ros_grant, grant)
                        self.assertEqual(status["restarts"], 0)
                        self.assertEqual(status["sensors"]["depth"]["state"], "fault")
                        self.assertEqual(
                            status["sensors"]["depth"]["authority_fault"], "clock_drift"
                        )
                        self.assertFalse(status["sensors"]["depth"]["available"])
                        self.assertEqual(runtime.snapshot("depth")["state"], "UNKNOWN")
                finally:
                    runtime.shutdown()

    def test_parent_renews_and_rejects_old_epoch_status(self):
        import queue

        with tempfile.TemporaryDirectory() as tmp:
            path, manifest = fixture(Path(tmp), version=2, renewal="software_fixture")
            pipeline = RuntimePipeline(load_config(path).profiles[0])
            helper = authority_fixture.RosAuthority()
            helper.setUp()
            helper.now = pipeline.ros_grant.issued_ns
            helper.wall_offset = -pipeline.ros_grant.offset_ns
            pipeline.ros_guard = helper.guard(pipeline.ros_grant, manifest)
            pipeline.process = object()
            pipeline.channel = queue.Queue()
            pipeline.ros_control = queue.Queue()
            helper.now += 15_000_000_000
            message = {
                "data": None,
                "reason": None,
                "latency_ms": 1.0,
                "sensor_state": "processing",
                "sensor_batches": 1,
                "sensor_expires_ns": helper.now + 50_000_000,
                "sensor_emitted_ns": helper.now,
                "sensor_generation": 0,
            }
            try:
                pipeline.channel.put(message)
                pipeline.tick(helper.now)
                self.assertEqual(pipeline.ros_grant.generation, 1)
                self.assertFalse(pipeline.sensor_status(helper.now)["available"])
                self.assertEqual(pipeline.ros_control.get_nowait()["grant"]["generation"], 1)
                pipeline.channel.put(message)  # Old worker status cannot revive old points.
                pipeline.tick(helper.now)
                self.assertFalse(pipeline.sensor_status(helper.now)["available"])
                pipeline.channel.put({**message, "sensor_generation": 1, "sensor_batches": 2})
                pipeline.tick(helper.now)
                self.assertTrue(pipeline.sensor_status(helper.now)["available"])
                self.assertEqual(pipeline.snapshot(helper.now)["state"], "UNKNOWN")
                # Tamper before the next renewal: no authority, even after crash/replacement.
                (Path(tmp) / "sensor.json").write_text("{}")
                helper.now += 15_000_000_000
                pipeline.channel.put(
                    {
                        **message,
                        "sensor_generation": 1,
                        "sensor_batches": 3,
                        "sensor_emitted_ns": helper.now,
                        "sensor_expires_ns": helper.now + 50_000_000,
                    }
                )
                pipeline.tick(helper.now)
                self.assertFalse(pipeline.sensor_status(helper.now)["available"])
                replacement = RuntimePipeline(
                    pipeline.profile, ros_grant=pipeline.ros_grant, ros_guard=pipeline.ros_guard
                )
                self.assertFalse(replacement.ros_guard.check())
                replacement.close()
            finally:
                pipeline.process = None
                pipeline.close()

    def test_closed_profile_and_signed_manifest_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, manifest = fixture(root)
            config = load_config(path)
            profile = config.profiles[0]
            self.assertEqual(profile.address, manifest.topic)
            for change in (
                {"sensor_manifest": None},
                {"model": "anything.onnx"},
                {"address": "/other"},
            ):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    p = Profile.model_validate({**profile.model_dump(), **change})
                    RuntimePipeline(p)
            config.integrity_bundle = str(root)
            config.trust_root = str(root / "trust.pub")
            with patch(
                "aethron_edge.runtime.updates.verify_bundle",
                return_value={"files": {"appliance.json": "unused"}},
            ):
                with self.assertRaises(ValueError):
                    verify_configuration(config, path)
            alias = root / "alias.json"
            alias.symlink_to(root / "sensor.json")
            text = json.loads(path.read_text())
            text["profiles"][0]["sensor_manifest"] = alias.name
            path.write_text(json.dumps(text))
            with self.assertRaises(ValueError):
                load_config(path)

    def test_replacement_retains_original_boot_and_expiry_and_parent_withdraws(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = fixture(Path(tmp))
            profile = load_config(path).profiles[0]
            pipeline = RuntimePipeline(profile)
            replacement = RuntimePipeline(profile, ros_grant=pipeline.ros_grant)
            try:
                self.assertEqual(replacement.ros_grant, pipeline.ros_grant)
                replacement.sensor_state = "processing"
                replacement.sensor_emitted_ns = replacement.ros_grant.valid_until_ns
                replacement.sensor_expires_ns = replacement.ros_grant.valid_until_ns + 99999999
                replacement.process = object()  # No SDK required to exercise parent expiry.
                status = replacement.sensor_status(replacement.ros_grant.valid_until_ns + 1)
                self.assertFalse(status["available"])
                self.assertEqual(status["source_evidence"], "external_unverified")
                self.assertFalse(status["qualified"])
                replacement.process = None
            finally:
                pipeline.close()
                replacement.close()

    def test_missing_optional_ros_sdk_withdraws_without_private_echo(self):
        import threading

        from aethron_edge.sensors.ros_worker import ros_worker

        with tempfile.TemporaryDirectory() as tmp:
            path, _ = fixture(Path(tmp))
            profile = load_config(path).profiles[0]
            pipeline = RuntimePipeline(profile)
            messages = []
            try:
                with patch.dict("os.environ"), patch.dict("sys.modules", {"rclpy.context": None}):
                    ros_worker(profile, pipeline.ros_grant, messages.append, threading.Event())
                self.assertEqual(messages[-1]["sensor_state"], "fault")
                self.assertIsNone(messages[-1]["data"])
                self.assertEqual(messages[-1]["sensor_expires_ns"], 0)
                self.assertNotIn(tmp, json.dumps(messages))
            finally:
                pipeline.close()
