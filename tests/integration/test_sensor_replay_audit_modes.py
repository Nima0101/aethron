"""Evidence checks must not disappear under interpreter optimization."""

import contextlib
import io
import os
import runpy
import subprocess
import sys
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/probes/sensor_replay_audit/compare.py"


class ReplayAuditModeTests(unittest.TestCase):
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
                self.assertEqual(result.stderr.strip(), "replay_audit_requires_assertions")

    def test_normal_mode_rejects_wrong_timed_and_traced_results_without_report(self):
        for fail_at in (1, 2):
            with self.subTest(fail_at=fail_at):
                module = runpy.run_path(str(PROBE))
                calls = []

                def candidate(stream, size, calls=calls, fail_at=fail_at):
                    calls.append(size)
                    return b"wrong" if len(calls) == fail_at else stream.read(size)

                output = io.StringIO()
                with patch.dict(module["main"].__globals__, baseline=candidate):
                    with contextlib.redirect_stdout(output):
                        with self.assertRaises(AssertionError):
                            module["main"]()
                self.assertEqual(len(calls), fail_at)
                self.assertEqual(output.getvalue(), "")
                self.assertFalse(tracemalloc.is_tracing())
