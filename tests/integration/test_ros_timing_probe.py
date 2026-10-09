"""Test-only instrumentation must explain rejection without changing admission."""

import importlib.util
import io
import json
import unittest
from pathlib import Path

import test_sensor_ros_authority as authority_fixture
from aethron_edge.sensors.ros2 import ClockMapping, RosIngress
from test_sensor_ros2 import image

PROBE = Path(__file__).resolve().parents[1] / "ros2/ros_timing_probe.py"


class TimingProbe(unittest.TestCase):
    def api(self):
        path = (
            PROBE if PROBE.is_file() else Path(importlib.util.find_spec("ros_timing_probe").origin)
        )
        spec = importlib.util.spec_from_file_location("ros_timing_probe", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_stale_frame_is_still_rejected_and_probe_retains_only_deltas(self):
        probe = self.api()
        rows = []
        bridge = RosIngress(modality="depth", frame_id="front_optical", meters_per_unit=0.001)
        bridge.bind_clock(
            ClockMapping(
                domain="ros_system", offset_ns=0, uncertainty_ns=0, valid_until_ns=5_000_000_000
            )
        )
        with probe.instrument(rows.append):
            result = bridge.image(image(), now_ns=1_200_000_000)
        self.assertEqual(result.reason, "clock_discontinuity")
        self.assertIsNone(bridge.mapping)
        self.assertEqual(
            rows,
            [
                {
                    "event": "source_rejected",
                    "age_ns": 200_000_000,
                    "uncertainty_ns": 0,
                    "stamp_delta_ns": None,
                    "receive_delta_ns": None,
                }
            ],
        )

    def test_clock_drift_is_not_remapped_and_instrumentation_restores_methods(self):
        probe = self.api()
        f = authority_fixture.RosAuthority()
        f.setUp()
        guard = f.guard()
        cls = type(guard)
        original = cls.check
        rows = []
        with probe.instrument(rows.append):
            f.wall_offset += 2_000_001
            self.assertFalse(guard.check())
        self.assertIs(cls.check, original)
        self.assertEqual(guard.fault, "clock_drift")
        self.assertEqual(
            rows,
            [
                {
                    "event": "clock_rejected",
                    "sample_ns": 0,
                    "offset_delta_ns": -2_000_001,
                    "sample_error_ns": 0,
                    "grant_sample_error_ns": 0,
                    "budget_ns": 1_000_000,
                }
            ],
        )

    def test_log_extraction_is_bounded_and_refuses_foreign_fields_and_types(self):
        probe = self.api()
        valid = {
            "event": "source_rejected",
            "age_ns": 200_000_000,
            "uncertainty_ns": 0,
            "stamp_delta_ns": None,
            "receive_delta_ns": None,
        }
        bad = [
            {**valid, "identity": "private"},
            {**valid, "age_ns": True},
            {**valid, "age_ns": "private"},
            {**valid, "age_ns": 2**100},
        ]
        log = io.BytesIO(
            b"private unrelated log\n"
            + b"".join(
                b"AETHRON_TIMING " + json.dumps(r).encode() + b"\n" for r in bad + [valid] * 20
            )
        )
        self.assertEqual(probe.read_rows(log), [valid] * 8)
        self.assertLessEqual(probe.MAX_LOG_BYTES, 65536)
        self.assertNotIn("private", json.dumps(probe.read_rows(log)))

    def test_probe_caps_emission_and_a_broken_sink_cannot_prevent_revocation(self):
        probe = self.api()
        rows = []

        def reject():
            bridge = RosIngress(modality="depth", frame_id="front_optical", meters_per_unit=0.001)
            bridge.bind_clock(
                ClockMapping(
                    domain="ros_system", offset_ns=0, uncertainty_ns=0, valid_until_ns=5_000_000_000
                )
            )
            self.assertEqual(
                bridge.image(image(), now_ns=1_200_000_000).reason, "clock_discontinuity"
            )
            self.assertIsNone(bridge.mapping)

        with probe.instrument(rows.append):
            for _ in range(20):
                reject()
        self.assertEqual(len(rows), 8)

        def broken_sink(row):
            raise OSError("log unavailable")

        with probe.instrument(broken_sink):
            reject()

    def test_future_and_duplicate_frames_are_distinguishable_without_source_stamps(self):
        probe = self.api()
        for future in (False, True):
            with self.subTest(future=future):
                bridge = RosIngress(
                    modality="depth", frame_id="front_optical", meters_per_unit=0.001
                )
                bridge.bind_clock(
                    ClockMapping(
                        domain="ros_system",
                        offset_ns=0,
                        uncertainty_ns=0,
                        valid_until_ns=5_000_000_000,
                    )
                )
                bridge.image(image(), now_ns=1_020_000_000)
                rows = []
                with probe.instrument(rows.append):
                    result = bridge.image(
                        image(1_040_000_000 if future else 1_000_000_000), now_ns=1_030_000_000
                    )
                self.assertEqual(result.reason, "clock_discontinuity")
                self.assertEqual(rows[0]["age_ns"], -10_000_000 if future else 30_000_000)
                self.assertEqual(rows[0]["stamp_delta_ns"], 40_000_000 if future else 0)
                self.assertEqual(rows[0]["receive_delta_ns"], 10_000_000)

    def test_explicit_child_startup_hook_captures_real_rejection(self):
        import os
        import subprocess
        import sys
        import tempfile

        probe = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Keep the same installed/source closure when changing the child's cwd.
            env = dict(
                os.environ,
                PYTHONPATH=os.pathsep.join(str(Path(p or ".").resolve()) for p in sys.path),
            )
            env = probe.child_environment(root / "probe", env)
            code = """
from aethron_edge.sensors.ros2 import ClockMapping, RosIngress
from test_sensor_ros2 import image
bridge=RosIngress(modality="depth",frame_id="front_optical",meters_per_unit=0.001)
bridge.bind_clock(ClockMapping(domain="ros_system",offset_ns=0,uncertainty_ns=0,valid_until_ns=5000000000))
assert bridge.image(image(),now_ns=1200000000).reason=="clock_discontinuity"
assert bridge.mapping is None
"""
            result = subprocess.run(
                [sys.executable, "-c", code],
                env=env,
                cwd=root,
                capture_output=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = probe.read_rows(io.BytesIO(result.stderr))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["age_ns"], 200_000_000)
