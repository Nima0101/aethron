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
import tracemalloc
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aethron_edge.sensors import replay

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/probes/sensor_replay_audit/compare.py"


class ReplayAuditModeTests(unittest.TestCase):
    def diagnostic_report(self):
        main = runpy.run_path(str(PROBE))["main"]
        payload = b"x" * (1024 * 1024)
        output = io.StringIO()
        fake_trace = SimpleNamespace(
            is_tracing=lambda: False,
            start=Mock(),
            stop=Mock(),
            get_traced_memory=lambda: (0, 0),
        )
        with (
            patch.dict(
                main.__globals__,
                {
                    **{
                        name: lambda *args: payload
                        for name in ("baseline", "direct", "readinto", "_read")
                    },
                    "time": SimpleNamespace(process_time_ns=lambda: 0, perf_counter_ns=lambda: 0),
                    "tracemalloc": fake_trace,
                    "tempfile": SimpleNamespace(TemporaryFile=io.BytesIO),
                },
            ),
            contextlib.redirect_stdout(output),
        ):
            main()
        return json.loads(output.getvalue())

    def test_report_pins_harness_and_actual_imported_module(self):
        with tempfile.TemporaryDirectory() as directory:
            installed = Path(directory) / "replay.py"
            installed.write_bytes(b"abc")
            with patch.object(replay, "__file__", str(installed)):
                report = self.diagnostic_report()
        self.assertIn("source_sha256", report)
        self.assertEqual(
            report["source_sha256"],
            {
                "compare.py": hashlib.sha256(PROBE.read_bytes()).hexdigest(),
                "aethron_edge.sensors.replay": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            },
        )
        self.assertNotIn(directory, json.dumps(report))

    def test_report_binds_exact_payload(self):
        report = self.diagnostic_report()
        self.assertIn("payload_sha256", report)
        self.assertEqual(report["payload_sha256"], hashlib.sha256(b"x" * (1024 * 1024)).hexdigest())
        self.assertEqual(report["payload_bytes"], 1024 * 1024)

    def test_missing_source_prevents_report_emission(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(replay, "__file__", str(Path(directory) / "missing.py")):
                with self.assertRaises(FileNotFoundError):
                    self.diagnostic_report()

    def test_existing_trace_session_rejects_before_fixture_creation(self):
        module = runpy.run_path(str(PROBE))
        output = io.StringIO()
        tracemalloc.start()
        retained = bytearray(32)
        try:
            with patch.object(module["tempfile"], "TemporaryFile") as create_file:
                create_file.side_effect = RuntimeError("fixture_creation_entered")
                with contextlib.redirect_stdout(output):
                    try:
                        module["main"]()
                    except Exception as exc:
                        failure = exc
                    else:
                        failure = None
                self.assertIs(type(failure), ValueError)
                self.assertEqual(str(failure), "replay_audit_tracing_active")
                create_file.assert_not_called()
            self.assertTrue(tracemalloc.is_tracing())
            self.assertIsNotNone(tracemalloc.get_object_traceback(retained))
            self.assertEqual(output.getvalue(), "")
        finally:
            tracemalloc.stop()

    def test_traced_candidate_failure_stops_owned_tracing_without_report(self):
        for failure_type in (RuntimeError, KeyboardInterrupt):
            with self.subTest(failure_type=failure_type):
                module = runpy.run_path(str(PROBE))
                calls = []

                def candidate(stream, size, failure_type=failure_type, calls=calls):
                    calls.append(tracemalloc.is_tracing())
                    if tracemalloc.is_tracing():
                        raise failure_type("synthetic_candidate_failure")
                    return stream.read(size)

                output = io.StringIO()
                try:
                    with patch.dict(module["main"].__globals__, baseline=candidate):
                        with contextlib.redirect_stdout(output):
                            with self.assertRaisesRegex(
                                failure_type, "synthetic_candidate_failure"
                            ):
                                module["main"]()
                    self.assertEqual(calls, [False, True])
                    self.assertEqual(output.getvalue(), "")
                    self.assertFalse(tracemalloc.is_tracing())
                finally:
                    tracemalloc.stop()

    def test_peak_read_failure_stops_owned_tracing_without_report(self):
        module = runpy.run_path(str(PROBE))
        output = io.StringIO()
        try:
            with patch.dict(
                module["main"].__globals__, baseline=lambda stream, size: stream.read(size)
            ):
                with patch.object(
                    tracemalloc,
                    "get_traced_memory",
                    side_effect=RuntimeError("synthetic_peak_failure"),
                ):
                    with contextlib.redirect_stdout(output):
                        with self.assertRaisesRegex(RuntimeError, "synthetic_peak_failure"):
                            module["main"]()
            self.assertEqual(output.getvalue(), "")
            self.assertFalse(tracemalloc.is_tracing())
        finally:
            tracemalloc.stop()

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
