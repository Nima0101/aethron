"""Evidence checks must not disappear under interpreter optimization."""

import os
import runpy
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/probes/sensor_packet_audit/compare.py"


class PacketAuditModeTests(unittest.TestCase):
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
