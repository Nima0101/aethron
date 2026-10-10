"""Evidence checks must not disappear under interpreter optimization."""

import io
import os
import runpy
import struct
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/probes/sensor_packet_audit/compare.py"


class PacketAuditModeTests(unittest.TestCase):
    def decode_worker_timing(self, duration):
        node_type = runpy.run_path(str(PROBE))["Node"]
        node = node_type.__new__(node_type)
        node.worker = SimpleNamespace(stdin=io.BytesIO())
        node.read = Mock(return_value=struct.pack("<dBdddd", duration, 1, 1, 2, 3, 0))
        layout = {
            "width": 1,
            "height": 1,
            "point_step": 12,
            "row_step": 12,
            "is_bigendian": False,
            "fields": [
                {"name": name, "offset": i * 4, "datatype": 7, "count": 1}
                for i, name in enumerate(("x", "y", "z"))
            ],
        }
        result = node.decode(layout, struct.pack("<fff", 1, 2, 3))
        return result, node.last_kernel_cpu_ms

    def test_worker_cpu_rejects_nonfinite_and_negative_reported_durations(self):
        for duration in (float("nan"), float("inf"), float("-inf"), -0.01):
            with self.subTest(duration=duration):
                with self.assertRaisesRegex(ValueError, "^invalid_worker_cpu_duration$"):
                    self.decode_worker_timing(duration)

    def test_worker_cpu_accepts_zero_and_positive_finite_durations(self):
        for duration in (0.0, 1.25):
            with self.subTest(duration=duration):
                result, observed = self.decode_worker_timing(duration)
                self.assertEqual(observed, duration)
                self.assertEqual(result.invalid_points, 0)
                self.assertEqual(result.points[0].xyz_m, (1.0, 2.0, 3.0))

    def test_optimized_import_rejects_before_exposing_unchecked_helpers(self):
        for flags, optimization in ((["-O"], ""), (["-OO"], ""), ([], "1"), ([], "2")):
            with self.subTest(flags=flags, optimization=optimization):
                env = dict(
                    os.environ,
                    PYTHONOPTIMIZE=optimization,
                    OPENBLAS_NUM_THREADS="1",
                    OMP_NUM_THREADS="1",
                    PYTHONPATH=str(ROOT / "integrations/edge"),
                )
                result = subprocess.run(
                    [
                        sys.executable,
                        *flags,
                        "-c",
                        "import runpy, sys; runpy.run_path(sys.argv[1]); print('unchecked_helpers_exposed')",
                        str(PROBE),
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr.strip(), "packet_audit_requires_assertions")

    def test_normal_mode_rejects_wrong_warmup_and_later_sample(self):
        measure = runpy.run_path(str(PROBE))["measure_all"]
        for values in (("wrong",), ("expected", "wrong")):
            with self.subTest(values=values):
                answers = iter(values)
                with self.assertRaises(AssertionError):
                    measure(
                        {"candidate": lambda *_, answers=answers: next(answers)},
                        {},
                        b"",
                        "expected",
                        None,
                    )

    def test_normal_mode_checks_warmup_and_all_fifteen_samples(self):
        measure = runpy.run_path(str(PROBE))["measure_all"]
        calls = []

        def candidate(layout, data):
            calls.append((layout, data))
            return "expected"

        report = measure({"candidate": candidate}, {}, b"", "expected", None)
        self.assertEqual(len(calls), 16)
        self.assertEqual(set(report), {"candidate"})
        self.assertTrue(all(value >= 0 for value in report["candidate"].values()))
