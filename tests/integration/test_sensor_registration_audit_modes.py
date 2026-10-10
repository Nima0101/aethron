"""Evidence checks must not disappear under interpreter optimization."""

import contextlib
import io
import json
import os
import runpy
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/probes/sensor_registration_audit/compare.py"


class RegistrationAuditModeTests(unittest.TestCase):
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
                self.assertEqual(result.stderr.strip(), "registration_audit_requires_assertions")

    def run_inert_comparison(self, output, *, mismatch_at=0, live_iterations=()):
        module = runpy.run_path(str(PROBE))
        bindings = []

        class InertRegistration:
            def __init__(self, *args, **kwargs):
                bindings.append(self)
                self.ordinal = len(bindings)

            def project(self, *args, **kwargs):
                return SimpleNamespace(
                    live_evidence=(self.ordinal - 1) // 5 in live_iterations,
                    value="wrong" if self.ordinal == mismatch_at else "same",
                )

        with patch.dict(module["main"].__globals__, Registration=InertRegistration):
            with contextlib.redirect_stdout(output):
                module["main"]()

    def test_earlier_and_final_mismatches_cannot_emit_parity_report(self):
        for ordinal in (2, 72):
            with self.subTest(binding=ordinal):
                output = io.StringIO()
                with self.assertRaises(AssertionError):
                    self.run_inert_comparison(output, mismatch_at=ordinal)
                self.assertEqual(output.getvalue(), "")

    def test_earlier_and_final_live_flags_cannot_emit_parity_report(self):
        for iteration in (0, 14):
            with self.subTest(iteration=iteration):
                output = io.StringIO()
                with self.assertRaises(AssertionError):
                    self.run_inert_comparison(output, live_iterations=(iteration,))
                self.assertEqual(output.getvalue(), "")

    def test_consistent_nonlive_results_can_emit_report(self):
        output = io.StringIO()
        self.run_inert_comparison(output)
        report = json.loads(output.getvalue())
        self.assertIs(report["parity"], True)
        self.assertEqual(report["samples"], 15)
        self.assertEqual(len(report["cpu_p50_ms"]), 5)
