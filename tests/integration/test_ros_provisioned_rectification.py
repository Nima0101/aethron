"""Versioned raw depth provisioning through installed manifest and worker paths."""

import json
import math
import tempfile
import threading
import types
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import test_ros_lens_rectification as lens_fixture
import test_sensor_ros_authority as authority_fixture
from aethron_edge.config import Profile
from aethron_edge.sensors.provider import GeometryProvider
from aethron_edge.sensors.ros_authority import ClockGuard, load_ros_manifest, read_ros_manifest
from aethron_edge.sensors.ros_worker import ros_worker
from aethron_edge.sources.base import SourceFault


class RawDepthProvisioning(unittest.TestCase):
    def setUp(self):
        self.lens_path = lens_fixture.RosLensBinding()
        self.lens_path.setup_path()
        self.helper = authority_fixture.RosAuthority()
        self.helper.setUp()
        self.helper.calibration = self.lens_path.fixture.config(lens=self.lens_path.lens)
        self.helper.now = self.lens_path.fixture.now
        self.helper.wall_offset = 0

    def raw(self, **changes):
        fields = {"version": 3, "image_geometry": "raw_distorted"}
        fields.update(changes)
        return self.helper.manifest(**fields)

    def test_explicit_version_binds_lens_and_roundtrips(self):
        try:
            m = self.raw()
        except ValueError:
            self.fail("explicit version3 raw-depth manifest is not implemented")
        self.assertEqual(load_ros_manifest(m.model_dump_json().encode()).digest, m.digest)
        self.assertEqual(m.calibration.lens, self.lens_path.lens)
        g = self.helper.grant(m)
        self.assertEqual(g.manifest_digest, m.digest)
        self.assertFalse(self.helper.guard(g, m).live_evidence)

    def test_legacy_versions_keep_digest_and_refuse_raw_fields(self):
        f = authority_fixture.RosAuthority()
        f.setUp()
        # Captured from installed 3cd62d3; not computed from the changed parser.
        self.assertEqual(
            f.manifest().digest, "f4722574ee25906e2a4d7abcc0b5c9892c423376f55d7eec46f979b5f709b02b"
        )
        self.assertEqual(
            f.manifest(version=2, renewal="software_fixture").digest,
            "00b0f3e811538a705f17c355e874dafa4eb3cee5a4182137a93eeb439d759796",
        )
        for version in (1, 2):
            with self.assertRaises(ValueError):
                self.helper.manifest(version=version)
            with self.assertRaises(ValueError):
                f.manifest(version=version, image_geometry="raw_distorted")

    def test_raw_mode_requires_lens_and_exact_version_and_cannot_promote_authority(self):
        for change in (
            {"version": 3.0},
            {"version": True},
            {"version": 4},
            {"image_geometry": "rectified"},
            {"image_geometry": None},
            {"calibration": self.lens_path.fixture.config().model_dump()},
            {"timestamp_authority": "hardware_exposure"},
            {"camera_info_topic": "/aethron/depth"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.raw(**change)
        with self.assertRaises(ValueError):
            self.helper.manifest(version=3)  # no implicit raw mode

    def test_raw_renewal_remains_synthetic_and_digest_bound(self):
        m = self.raw(renewal="software_fixture")
        guard = self.helper.guard(manifest=m)
        self.helper.now += m.valid_for_ns // 2
        successor = guard.renew(
            m, emitted_ns=self.helper.now, expires_ns=self.helper.now + 10_000_000
        )
        self.assertEqual(successor.generation, 1)
        changed = self.raw(renewal="software_fixture", topic="/changed")
        with self.assertRaises(ValueError):
            self.helper.guard(self.helper.grant(m), changed)
        config = self.helper.calibration.model_dump()
        config["rig"]["evidence"] = "external_unverified"
        with self.assertRaises(ValueError):
            self.raw(renewal="software_fixture", calibration=config)

    def test_actual_worker_uses_provisioned_lens_with_transport_double(self):
        results, messages = self.run_worker()
        self.assertNotIsInstance(results[0], SourceFault)
        self.assertAlmostEqual(results[0].points[0].camera_xyz_m[0], 5 * math.tan(0.5) + 0.5)
        self.assertEqual(messages[-1]["sensor_state"], "processing")
        self.assertEqual(messages[-1]["sensor_expires_ns"], 1_050_000_000)

    def test_missing_rectifier_does_not_report_processing(self):
        results, messages = self.run_worker(without_vision=True)
        self.assertEqual(results[0].reason, "provider_unavailable")
        self.assertEqual(messages[-1]["sensor_state"], "waiting")
        self.assertEqual(messages[-1]["sensor_expires_ns"], 0)

    def run_worker(self, *, without_vision=False):
        m = self.raw(indices=[[2, 1]])
        stop = threading.Event()
        messages, results = [], []
        helper, path = self.helper, self.lens_path

        class Context:
            def init(self, **kwargs):
                self.active = True

            def ok(self):
                return self.active

            def shutdown(self):
                self.active = False

        class Transport:
            # Only DDS transport is replaced; real decoding, lens inverse, provider,
            # authority, worker loop, local manifest read and status serialization run.
            def __init__(self, bridge, **kwargs):
                self.bridge = bridge

            def poll_geometry(self, provider, indices, *, mount_id, timeout_sec):
                self.bridge.camera_info(path.info, now_ns=helper.now, valid_for_ns=30_000_000)
                path.image(self.bridge)
                result = provider.ros(self.bridge, indices, mount_id=mount_id)
                results.append(result)
                stop.set()
                return result

            def close(self):
                pass

        def guard(grant, manifest, *, boot_id):
            return ClockGuard(
                grant,
                manifest,
                boot_id=boot_id,
                monotonic=lambda: helper.now,
                realtime=lambda: helper.now,
            )

        def provider(*args, **kwargs):
            return GeometryProvider(*args, **kwargs, clock=lambda: helper.now)

        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "sensor.json"
            manifest_path.write_text(m.model_dump_json())
            profile = Profile(
                name="depth",
                driver="sensor-ros",
                address=m.topic,
                sensor_manifest=str(manifest_path),
            )
            self.assertEqual(read_ros_manifest(profile).digest, m.digest)
            bad = profile.model_copy(update={"address": "/other"})
            with self.assertRaises(ValueError):
                read_ros_manifest(bad)
            module = types.ModuleType("rclpy.context")
            module.Context = Context
            with (
                patch.dict("os.environ"),
                patch.dict("sys.modules", {"rclpy.context": module}),
                patch("aethron_edge.sensors.ros_worker.RosSubscriber", Transport),
                patch("aethron_edge.sensors.ros_worker.ClockGuard", guard),
                patch("aethron_edge.sensors.ros_worker.GeometryProvider", provider),
                patch("aethron_edge.sensors.ros_worker.time.monotonic_ns", lambda: helper.now),
                patch.dict("sys.modules", {"cv2": None}) if without_vision else nullcontext(),
            ):
                ros_worker(profile, helper.grant(m), messages.append, stop)
            self.assertEqual(len(results), 1)
            self.assertIsNone(messages[-1]["data"])
            self.assertNotIn(tmp, json.dumps(messages))
            return results, messages
