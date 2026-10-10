"""Evidence checks must not disappear under interpreter optimization."""

import contextlib
import io
import os
import runpy
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/probes/sensor_geometry_audit/compare.py"


class GeometryAuditModeTests(unittest.TestCase):
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
