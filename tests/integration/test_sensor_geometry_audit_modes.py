"""Evidence checks must not disappear under interpreter optimization."""

import contextlib
import io
import json
import os
import runpy
import subprocess
import sys
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/probes/sensor_geometry_audit/compare.py"


class InertCamera:
    """Exercise harness control flow without executing geometry algorithms."""

    def __init__(self, **spec):
        pass

    def project(self, point):
        return (1.0, 2.0)

    def deproject(self, *args):
        return (1.0, 2.0, 3.0)

    def range_m(self, point):
        return 4.0


class GeometryAuditModeTests(unittest.TestCase):
    def test_existing_trace_session_rejects_before_camera_creation(self):
        module = runpy.run_path(str(PROBE))
        output = io.StringIO()
        tracemalloc.start()
        retained = bytearray(32)
        try:
            with patch.dict(module["main"].__globals__, Pinhole=None):
                with contextlib.redirect_stdout(output):
                    try:
                        module["main"]()
                    except Exception as exc:
                        failure = exc
                    else:
                        failure = None
            self.assertIsInstance(failure, ValueError)
            self.assertEqual(str(failure), "geometry_audit_tracing_active")
            self.assertTrue(tracemalloc.is_tracing())
            self.assertIsNotNone(tracemalloc.get_object_traceback(retained))
            self.assertEqual(output.getvalue(), "")
        finally:
            tracemalloc.stop()

    def test_traced_candidate_failure_stops_owned_tracing_without_report(self):
        for failure_type in (RuntimeError, KeyboardInterrupt):
            with self.subTest(failure_type=failure_type):
                module = runpy.run_path(str(PROBE))
                output = io.StringIO()

                def project(camera, point, failure_type=failure_type):
                    if tracemalloc.is_tracing():
                        raise failure_type("synthetic_traced_failure")
                    return (1.0, 2.0)

                try:
                    with (
                        patch.dict(
                            module["main"].__globals__,
                            Pinhole=InertCamera,
                            NumpyPinhole=InertCamera,
                        ),
                        patch.object(InertCamera, "project", project),
                    ):
                        with contextlib.redirect_stdout(output):
                            with self.assertRaisesRegex(failure_type, "^synthetic_traced_failure$"):
                                module["main"]()
                    self.assertFalse(tracemalloc.is_tracing())
                    self.assertEqual(output.getvalue(), "")
                finally:
                    tracemalloc.stop()

    def test_peak_read_failure_stops_owned_tracing_without_report(self):
        module = runpy.run_path(str(PROBE))
        output = io.StringIO()
        try:
            with (
                patch.dict(
                    module["main"].__globals__, Pinhole=InertCamera, NumpyPinhole=InertCamera
                ),
                patch.object(
                    tracemalloc, "get_traced_memory", side_effect=RuntimeError("peak_failure")
                ),
            ):
                with contextlib.redirect_stdout(output):
                    with self.assertRaisesRegex(RuntimeError, "^peak_failure$"):
                        module["main"]()
            self.assertFalse(tracemalloc.is_tracing())
            self.assertEqual(output.getvalue(), "")
        finally:
            tracemalloc.stop()

    def test_inert_success_reports_two_batches_and_releases_tracing(self):
        module = runpy.run_path(str(PROBE))
        output = io.StringIO()
        with (
            patch.dict(module["main"].__globals__, Pinhole=InertCamera, NumpyPinhole=InertCamera),
            contextlib.redirect_stdout(output),
        ):
            module["main"]()
        self.assertFalse(tracemalloc.is_tracing())
        report = json.loads(output.getvalue())
        self.assertEqual(set(report["batches"]), {"1", "64"})
        for batch in report["batches"].values():
            self.assertEqual(set(batch), {"production", "numpy"})
            for result in batch.values():
                self.assertGreaterEqual(result["traced_peak_bytes"], 0)

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
                self.assertEqual(result.stderr.strip(), "geometry_audit_requires_assertions")

    def test_admission_mismatch_emits_no_report(self):
        module = runpy.run_path(str(PROBE))
        output = io.StringIO()
        with patch.dict(
            module["main"].__globals__,
            outcome=lambda camera, operation, args: ("accepted", id(camera)),
        ):
            with contextlib.redirect_stdout(output):
                with self.assertRaises(AssertionError):
                    module["main"]()
        self.assertEqual(output.getvalue(), "")

    def test_warmup_mismatch_emits_no_report(self):
        module = runpy.run_path(str(PROBE))
        output = io.StringIO()
        with patch.object(module["np"], "allclose", return_value=False):
            with contextlib.redirect_stdout(output):
                with self.assertRaises(AssertionError):
                    module["main"]()
        self.assertEqual(output.getvalue(), "")
