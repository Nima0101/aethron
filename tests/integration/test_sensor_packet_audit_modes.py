"""Evidence checks must not disappear under interpreter optimization."""

import hashlib
import io
import json
import os
import runpy
import struct
import subprocess
import sys
import tempfile
import unittest
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from aethron_edge.sensors import packets

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/probes/sensor_packet_audit/compare.py"


class PacketAuditModeTests(unittest.TestCase):
    def setUp(self):
        # Check while fixtures are active: teardown restoration alone hides interference.
        self.shared_bindings = (
            subprocess.check_output,
            subprocess.Popen,
            Path.exists,
            Path.read_text,
            packets.__file__,
            sys.stdout,
        )

    def assert_shared_bindings_unchanged(self):
        for actual, expected in zip(
            (
                subprocess.check_output,
                subprocess.Popen,
                Path.exists,
                Path.read_text,
                packets.__file__,
                sys.stdout,
            ),
            self.shared_bindings,
            strict=True,
        ):
            self.assertIs(actual, expected)

    def diagnostic_report(
        self,
        worker_exit=0,
        output=None,
        on_close=None,
        harness_path=PROBE,
        packet_path=None,
    ):
        main = runpy.run_path(str(PROBE))["main"]
        worker = SimpleNamespace(
            decode=Mock(),
            startup_ms=0,
            rss_kib=None,
            close=Mock(side_effect=on_close),
            worker=SimpleNamespace(returncode=worker_exit),
        )
        fixtures = [({"marker": "first"}, b"abc"), ({"marker": "second"}, b"abd")]
        output = io.StringIO() if output is None else output
        with (
            patch.dict(
                main.__globals__,
                {
                    "__file__": str(harness_path),
                    "packets": SimpleNamespace(
                        __file__=packets.__file__ if packet_path is None else str(packet_path)
                    ),
                    "subprocess": SimpleNamespace(check_output=Mock(return_value="synthetic-node")),
                    "print": partial(print, file=output),
                    "fixture": Mock(side_effect=fixtures),
                    "scalar_baseline": Mock(
                        return_value=SimpleNamespace(
                            sample_points=[None] * 4096, invalid_points=241
                        )
                    ),
                    "Node": Mock(return_value=worker),
                    "measure_all": Mock(side_effect=[{"node_buffer": {}}, {"node_buffer": {}}]),
                },
            ),
        ):
            self.assert_shared_bindings_unchanged()
            main()
        return json.loads(output.getvalue())

    def test_changed_source_during_comparison_prevents_report(self):
        for name in ("compare.py", "buffer_worker.cjs", "packets.py"):
            with self.subTest(source=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for filename in ("compare.py", "buffer_worker.cjs", "packets.py"):
                    (root / filename).write_bytes(b"before")
                mutation = Mock(side_effect=lambda target=root / name: target.write_bytes(b"after"))
                output = io.StringIO()
                with self.assertRaisesRegex(RuntimeError, "^audit_source_changed$"):
                    self.diagnostic_report(
                        on_close=mutation,
                        harness_path=root / "compare.py",
                        output=output,
                        packet_path=root / "packets.py",
                    )
                self.assertEqual(mutation.call_count, 2)
                self.assertEqual(output.getvalue(), "")

    def test_removed_source_during_comparison_prevents_report(self):
        for name in ("compare.py", "buffer_worker.cjs", "packets.py"):
            with self.subTest(source=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for filename in ("compare.py", "buffer_worker.cjs", "packets.py"):
                    (root / filename).write_bytes(b"before")
                removal = Mock(
                    side_effect=lambda target=root / name: target.unlink(missing_ok=True)
                )
                output = io.StringIO()
                with self.assertRaises(FileNotFoundError):
                    self.diagnostic_report(
                        on_close=removal,
                        harness_path=root / "compare.py",
                        output=output,
                        packet_path=root / "packets.py",
                    )
                self.assertEqual(removal.call_count, 2)
                self.assertEqual(output.getvalue(), "")

    def test_version_query_requests_finite_timeout(self):
        main = runpy.run_path(str(PROBE))["main"]
        fixture, worker = Mock(), Mock()
        output = io.StringIO()
        query = Mock(side_effect=subprocess.TimeoutExpired("node", 5))
        with patch.dict(
            main.__globals__,
            {
                "fixture": fixture,
                "Node": worker,
                "subprocess": SimpleNamespace(check_output=query),
                "print": partial(print, file=output),
            },
        ):
            self.assert_shared_bindings_unchanged()
            with self.assertRaises(subprocess.TimeoutExpired):
                main()
        query.assert_called_once_with(["node", "--version"], text=True, timeout=5)
        fixture.assert_not_called()
        worker.assert_not_called()
        self.assertEqual(output.getvalue(), "")

    def test_version_query_failures_abort_before_comparison_or_report(self):
        for failure in (
            OSError("synthetic_spawn_failure"),
            subprocess.CalledProcessError(1, ["node", "--version"]),
            subprocess.TimeoutExpired("node", 5),
        ):
            with self.subTest(failure=type(failure).__name__):
                main = runpy.run_path(str(PROBE))["main"]
                fixture, worker = Mock(), Mock()
                output = io.StringIO()
                with patch.dict(
                    main.__globals__,
                    {
                        "fixture": fixture,
                        "Node": worker,
                        "subprocess": SimpleNamespace(check_output=Mock(side_effect=failure)),
                        "print": partial(print, file=output),
                    },
                ):
                    self.assert_shared_bindings_unchanged()
                    with self.assertRaises(type(failure)) as result:
                        main()
                self.assertIs(result.exception, failure)
                fixture.assert_not_called()
                worker.assert_not_called()
                self.assertEqual(output.getvalue(), "")

    def test_abnormal_or_unconfirmed_worker_exit_prevents_report(self):
        for status in (1, -9, None):
            with self.subTest(status=status):
                output = io.StringIO()
                with self.assertRaisesRegex(RuntimeError, "^audit_worker_exit$"):
                    self.diagnostic_report(worker_exit=status, output=output)
                self.assertEqual(output.getvalue(), "")

    def test_successful_worker_exit_allows_complete_report(self):
        report = self.diagnostic_report(worker_exit=0)
        self.assertEqual(len(report["cases"]), 2)
        self.assertTrue(all(case["parity"] for case in report["cases"]))

    def test_report_pins_probe_worker_and_actual_imported_module(self):
        with tempfile.TemporaryDirectory() as directory:
            installed = Path(directory) / "packets.py"
            installed.write_bytes(b"abc")
            report = self.diagnostic_report(packet_path=installed)
        self.assertIn("source_sha256", report)
        self.assertEqual(
            report["source_sha256"],
            {
                "compare.py": hashlib.sha256(PROBE.read_bytes()).hexdigest(),
                "buffer_worker.cjs": hashlib.sha256(
                    PROBE.with_name("buffer_worker.cjs").read_bytes()
                ).hexdigest(),
                "aethron_edge.sensors.packets": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            },
        )
        self.assertNotIn(directory, json.dumps(report))

    def test_report_binds_each_exact_fixture_payload_and_layout(self):
        report = self.diagnostic_report()
        for case, marker, payload in zip(
            report["cases"], ("first", "second"), (b"abc", b"abd"), strict=True
        ):
            with self.subTest(marker=marker):
                self.assertIn("fixture_sha256", case)
                self.assertEqual(
                    case["fixture_sha256"],
                    {
                        "payload": hashlib.sha256(payload).hexdigest(),
                        "layout_json": hashlib.sha256(
                            json.dumps(
                                {"marker": marker},
                                sort_keys=True,
                                separators=(",", ":"),
                                allow_nan=False,
                            ).encode("utf-8")
                        ).hexdigest(),
                    },
                )

    def test_missing_source_prevents_report_emission(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                self.diagnostic_report(packet_path=Path(directory) / "missing.py")

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
                    patch.dict(
                        module["Node"].__init__.__globals__,
                        {
                            "subprocess": SimpleNamespace(
                                Popen=Mock(return_value=worker), PIPE=subprocess.PIPE
                            ),
                        },
                    ),
                    patch.object(module["Node"], "read", reader),
                ):
                    self.assert_shared_bindings_unchanged()
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
            patch.dict(
                module["Node"].__init__.__globals__,
                {
                    "subprocess": SimpleNamespace(
                        Popen=Mock(return_value=worker), PIPE=subprocess.PIPE
                    ),
                },
            ),
            patch.object(module["Node"], "read", return_value=b"\1"),
            patch.dict(
                module["Node"].__init__.__globals__,
                {
                    "Path": Mock(
                        side_effect=[
                            PROBE,
                            SimpleNamespace(
                                exists=lambda: True, read_text=lambda: "VmRSS: invalid kB"
                            ),
                        ]
                    ),
                },
            ),
        ):
            self.assert_shared_bindings_unchanged()
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
            patch.dict(
                module["Node"].__init__.__globals__,
                {
                    "subprocess": SimpleNamespace(
                        Popen=Mock(return_value=worker), PIPE=subprocess.PIPE
                    ),
                },
            ),
            patch.object(module["Node"], "read", return_value=b"\1"),
            patch.dict(
                module["Node"].__init__.__globals__,
                {
                    "Path": Mock(side_effect=[PROBE, SimpleNamespace(exists=lambda: False)]),
                },
            ),
        ):
            self.assert_shared_bindings_unchanged()
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
