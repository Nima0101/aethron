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
from unittest.mock import Mock, call, patch

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/probes/sensor_packet_audit/compare.py"


class PacketAuditModeTests(unittest.TestCase):
    def diagnostic_node(self):
        node_type = runpy.run_path(str(PROBE))["Node"]
        node = node_type.__new__(node_type)
        node.worker = SimpleNamespace(
            stdin=Mock(),
            stdout=Mock(),
            stderr=Mock(),
            wait=Mock(),
            poll=Mock(return_value=0),
            kill=Mock(),
        )
        return node

    def test_stdin_close_failure_does_not_skip_wait_or_output_cleanup(self):
        for failure in (BrokenPipeError("stdin_close"), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                node = self.diagnostic_node()
                node.worker.stdin.close.side_effect = failure
                with self.assertRaises(type(failure)):
                    node.close()
                node.worker.wait.assert_called_once_with(timeout=5)
                node.worker.stdout.close.assert_called_once_with()
                node.worker.stderr.close.assert_called_once_with()

    def test_process_cleanup_failure_still_attempts_both_output_closes(self):
        for operation in ("poll", "kill", "post_kill_wait"):
            with self.subTest(operation=operation):
                node = self.diagnostic_node()
                worker = node.worker
                worker.poll.return_value = None
                failure = OSError("synthetic_cleanup_failure")
                if operation == "post_kill_wait":
                    worker.wait.side_effect = [None, failure]
                else:
                    getattr(worker, operation).side_effect = failure
                with self.assertRaisesRegex(OSError, "^synthetic_cleanup_failure$"):
                    node.close()
                worker.stdout.close.assert_called_once_with()
                worker.stderr.close.assert_called_once_with()

    def test_stdout_close_failure_still_attempts_stderr_close(self):
        node = self.diagnostic_node()
        node.worker.stdout.close.side_effect = OSError("stdout_close")
        with self.assertRaisesRegex(OSError, "^stdout_close$"):
            node.close()
        node.worker.stderr.close.assert_called_once_with()

    def test_timeout_kills_worker_and_uses_timed_second_wait(self):
        for second_failure in (None, subprocess.TimeoutExpired("synthetic", 5)):
            with self.subTest(second_failure=second_failure):
                node = self.diagnostic_node()
                worker = node.worker
                worker.poll.return_value = None
                worker.wait.side_effect = [
                    subprocess.TimeoutExpired("synthetic", 5),
                    second_failure,
                ]
                with self.assertRaises(subprocess.TimeoutExpired):
                    node.close()
                worker.kill.assert_called_once_with()
                self.assertEqual(worker.wait.call_args_list, [call(timeout=5), call(timeout=5)])
                worker.stdout.close.assert_called_once_with()
                worker.stderr.close.assert_called_once_with()

    def test_completed_worker_closes_all_pipes_without_kill(self):
        node = self.diagnostic_node()
        node.close()
        node.worker.wait.assert_called_once_with(timeout=5)
        node.worker.kill.assert_not_called()
        for pipe in (node.worker.stdin, node.worker.stdout, node.worker.stderr):
            pipe.close.assert_called_once_with()

    def test_failed_worker_startup_releases_process_and_pipes(self):
        for failure in (b"\0", TimeoutError("startup_timeout"), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                module = runpy.run_path(str(PROBE))
                worker = SimpleNamespace(
                    stdin=io.BytesIO(),
                    stdout=io.BytesIO(),
                    stderr=io.BytesIO(),
                    wait=Mock(),
                    poll=Mock(return_value=0),
                    kill=Mock(),
                    pid=123,
                )
                reader = (
                    Mock(return_value=failure)
                    if isinstance(failure, bytes)
                    else Mock(side_effect=failure)
                )
                expected = AssertionError if isinstance(failure, bytes) else type(failure)
                with (
                    patch.object(module["subprocess"], "Popen", return_value=worker),
                    patch.object(module["Node"], "read", reader),
                ):
                    with self.assertRaises(expected):
                        module["Node"]({})
                self.assertTrue(worker.stdin.closed)
                self.assertTrue(worker.stdout.closed)
                self.assertTrue(worker.stderr.closed)
                worker.wait.assert_called_once_with(timeout=5)
                worker.kill.assert_not_called()

    def test_failed_startup_metadata_releases_worker(self):
        module = runpy.run_path(str(PROBE))
        worker = SimpleNamespace(
            stdin=io.BytesIO(),
            stdout=io.BytesIO(),
            stderr=io.BytesIO(),
            wait=Mock(),
            poll=Mock(return_value=0),
            kill=Mock(),
            pid=123,
        )
        with (
            patch.object(module["subprocess"], "Popen", return_value=worker),
            patch.object(module["Node"], "read", return_value=b"\1"),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value="VmRSS: invalid kB"),
        ):
            with self.assertRaises(ValueError):
                module["Node"]({})
        self.assertTrue(worker.stdin.closed)
        self.assertTrue(worker.stdout.closed)
        self.assertTrue(worker.stderr.closed)
        worker.wait.assert_called_once_with(timeout=5)

    def test_successful_startup_keeps_worker_available_until_close(self):
        module = runpy.run_path(str(PROBE))
        worker = SimpleNamespace(
            stdin=io.BytesIO(),
            stdout=io.BytesIO(),
            stderr=io.BytesIO(),
            wait=Mock(),
            poll=Mock(return_value=0),
            kill=Mock(),
            pid=123,
        )
        with (
            patch.object(module["subprocess"], "Popen", return_value=worker),
            patch.object(module["Node"], "read", return_value=b"\1"),
            patch.object(Path, "exists", return_value=False),
        ):
            node = module["Node"]({})
        worker.wait.assert_not_called()
        self.assertFalse(worker.stdin.closed)
        self.assertIsNone(node.rss_kib)
        self.assertGreaterEqual(node.startup_ms, 0)
        node.close()
        self.assertTrue(worker.stdin.closed)
        self.assertTrue(worker.stdout.closed)
        self.assertTrue(worker.stderr.closed)

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
