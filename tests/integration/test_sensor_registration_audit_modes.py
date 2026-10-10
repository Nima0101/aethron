"""Evidence checks must not disappear under interpreter optimization."""

import contextlib
import hashlib
import io
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aethron_edge.sensors import registration

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/probes/sensor_registration_audit/compare.py"


class RegistrationAuditModeTests(unittest.TestCase):
    def test_changed_source_during_comparison_prevents_report(self):
        for name in ("compare.py", "registration.py"):
            with self.subTest(source=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for filename in ("compare.py", "registration.py"):
                    (root / filename).write_bytes(b"before")
                mutation = Mock(side_effect=lambda target=root / name: target.write_bytes(b"after"))
                output = io.StringIO()
                transform = registration.RigCalibration.transform
                digest = registration.RigCalibration.digest
                with patch.object(registration, "__file__", str(root / "registration.py")):
                    with self.assertRaisesRegex(
                        RuntimeError, "^registration_audit_source_changed$"
                    ):
                        self.run_inert_comparison(
                            output, on_binding=mutation, harness_path=root / "compare.py"
                        )
                self.assertTrue(mutation.called)
                self.assertEqual(output.getvalue(), "")
                self.assertIs(registration.RigCalibration.transform, transform)
                self.assertIs(registration.RigCalibration.digest, digest)

    def test_removed_source_during_comparison_prevents_report(self):
        for name in ("compare.py", "registration.py"):
            with self.subTest(source=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for filename in ("compare.py", "registration.py"):
                    (root / filename).write_bytes(b"before")
                removal = Mock(
                    side_effect=lambda target=root / name: target.unlink(missing_ok=True)
                )
                output = io.StringIO()
                transform = registration.RigCalibration.transform
                digest = registration.RigCalibration.digest
                with patch.object(registration, "__file__", str(root / "registration.py")):
                    with self.assertRaises(FileNotFoundError):
                        self.run_inert_comparison(
                            output, on_binding=removal, harness_path=root / "compare.py"
                        )
                self.assertTrue(removal.called)
                self.assertEqual(output.getvalue(), "")
                self.assertIs(registration.RigCalibration.transform, transform)
                self.assertIs(registration.RigCalibration.digest, digest)

    def test_report_pins_harness_and_actual_imported_registration(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            installed = Path(directory) / "registration.py"
            installed.write_bytes(b"abc")
            with patch.object(registration, "__file__", str(installed)):
                self.run_inert_comparison(output)
        report = json.loads(output.getvalue())
        self.assertIn("source_sha256", report)
        self.assertEqual(
            report["source_sha256"],
            {
                "compare.py": hashlib.sha256(PROBE.read_bytes()).hexdigest(),
                "aethron_edge.sensors.registration": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            },
        )
        self.assertNotIn(directory, output.getvalue())

    def test_missing_source_prevents_report_emission(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(registration, "__file__", str(Path(directory) / "missing.py")):
                with self.assertRaises(FileNotFoundError):
                    self.run_inert_comparison(output)
        self.assertEqual(output.getvalue(), "")

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

    def run_inert_comparison(
        self, output, *, mismatch_at=0, live_iterations=(), on_binding=None, harness_path=PROBE
    ):
        module = runpy.run_path(str(PROBE))
        bindings = []

        class InertRegistration:
            def __init__(self, *args, **kwargs):
                bindings.append(self)
                self.ordinal = len(bindings)
                if on_binding is not None:
                    on_binding()

            def project(self, *args, **kwargs):
                return SimpleNamespace(
                    live_evidence=(self.ordinal - 1) // 5 in live_iterations,
                    value="wrong" if self.ordinal == mismatch_at else "same",
                )

        with patch.dict(
            module["main"].__globals__, Registration=InertRegistration, __file__=str(harness_path)
        ):
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
