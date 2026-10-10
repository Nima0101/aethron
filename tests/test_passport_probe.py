"""The comparison probe must not emit evidence with assertions disabled."""

import asyncio
import contextlib
import hashlib
import io
import json
import runpy
import subprocess
import sys
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch


class ProbeExecutionTests(unittest.TestCase):
    def test_optimized_execution_is_rejected_without_evidence(self):
        root = Path(__file__).resolve().parents[1] / "scripts"
        for name in ("passport_technology_probe.py", "passport_trust_review.py"):
            for option in ("-O", "-OO"):
                with self.subTest(script=name, option=option):
                    result = subprocess.run(
                        [sys.executable, "-I", option, str(root / name)],
                        capture_output=True,
                        text=True,
                        timeout=25,
                        check=False,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("optimized_probe_execution_forbidden", result.stderr)
                    self.assertEqual(result.stdout, "")

    def test_startup_tracing_is_rejected_without_evidence(self):
        script = Path(__file__).resolve().parents[1] / "scripts/passport_technology_probe.py"
        result = subprocess.run(
            [sys.executable, "-I", "-X", "tracemalloc=3", str(script)],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("probe_tracing_already_active", result.stderr)
        self.assertEqual(result.stdout, "")


class ProbeResponseTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.main = runpy.run_path(str(root / "scripts/passport_technology_probe.py"))["main"]
        self.response = {
            "node": "v22.0.0",
            "crypto_accepts": [True, True, True, True, False, True],
            "hash_digest": hashlib.sha256(b"a" * 65536).hexdigest(),
            "hash_1mib_ms": 1.25,
            "duplicate_keys_collapsed": True,
            "float_lexemes_collapsed": True,
        }

    def invoke(self, raw, output):
        with (
            patch("shutil.which", return_value="node"),
            patch.dict(self.main.__globals__, {"_capture": lambda *args: raw}),
            contextlib.redirect_stdout(output),
        ):
            self.main()

    def test_valid_comparison_is_retained(self):
        for elapsed in (0, 1.25):
            with self.subTest(elapsed=elapsed):
                self.response["hash_1mib_ms"] = elapsed
                output = io.StringIO()
                self.invoke(json.dumps(self.response).encode(), output)
                result = json.loads(output.getvalue())
                self.assertEqual(result["node_probe"], self.response)
                self.assertEqual(result["cases"], 6)
                self.assertGreater(result["python_traced_peak_bytes"], 0)
                self.assertFalse(tracemalloc.is_tracing())
                self.assertEqual(result["audit_policy_version"], 3)
                self.assertEqual(result["python_lexical_rejections"], 5)

    def test_existing_tracing_is_preserved_without_running_probe(self):
        output = io.StringIO()
        tracemalloc.start(3)
        try:
            retained = bytearray(8192)
            with patch.dict(
                self.main.__globals__,
                {"verify": unittest.mock.Mock(wraps=self.main.__globals__["verify"])},
            ) as namespace:
                with self.assertRaisesRegex(RuntimeError, "probe_tracing_already_active"):
                    self.invoke(json.dumps(self.response).encode(), output)
                namespace["verify"].assert_not_called()
            self.assertTrue(tracemalloc.is_tracing())
            self.assertEqual(tracemalloc.get_traceback_limit(), 3)
            self.assertIsNotNone(tracemalloc.get_object_traceback(retained))
            self.assertEqual(output.getvalue(), "")
        finally:
            tracemalloc.stop()

    def test_measurement_failure_stops_owned_tracing_without_evidence(self):
        original = self.main.__globals__["verify"]
        for exception in (RuntimeError("measurement failed"), KeyboardInterrupt()):
            with self.subTest(exception=type(exception).__name__):
                output = io.StringIO()

                def fail_measurement(raw, *args, failure=exception, **kwargs):
                    if raw.startswith(b"["):
                        self.assertTrue(tracemalloc.is_tracing())
                        raise failure
                    return original(raw, *args, **kwargs)

                try:
                    with patch.dict(self.main.__globals__, {"verify": fail_measurement}):
                        with self.assertRaises(type(exception)) as raised:
                            self.invoke(json.dumps(self.response).encode(), output)
                    self.assertIs(raised.exception, exception)
                    self.assertFalse(tracemalloc.is_tracing())
                    self.assertEqual(output.getvalue(), "")
                finally:
                    tracemalloc.stop()

    def test_peak_read_failure_stops_owned_tracing_without_evidence(self):
        output = io.StringIO()
        try:
            with patch("tracemalloc.get_traced_memory", side_effect=RuntimeError("peak failed")):
                with self.assertRaisesRegex(RuntimeError, "peak failed"):
                    self.invoke(json.dumps(self.response).encode(), output)
            self.assertFalse(tracemalloc.is_tracing())
            self.assertEqual(output.getvalue(), "")
        finally:
            tracemalloc.stop()

    def test_comparison_records_project_source_digests(self):
        output = io.StringIO()
        self.invoke(json.dumps(self.response).encode(), output)
        report = json.loads(output.getvalue())
        self.assertIn("source_sha256", report)
        paths = {
            "scripts/passport_technology_probe.py",
            "scripts/passport_technology_probe.mjs",
            "aethron/passports.py",
            "aethron/_json_bounds.py",
            "examples/passports/vectors.json",
        }
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(set(report["source_sha256"]), paths)
        for name in paths:
            self.assertEqual(
                report["source_sha256"][name],
                hashlib.sha256((root / name).read_bytes()).hexdigest(),
            )

    def test_mutation_records_direct_helper_and_fixture_digests(self):
        root = Path(__file__).resolve().parents[1]
        main = runpy.run_path(str(root / "scripts/passport_trust_review.py"))["main"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main()
        report = json.loads(output.getvalue())
        paths = {
            "aethron/passports.py",
            "aethron/_json_bounds.py",
            "tests/test_passports.py",
            "scripts/passport_trust_review.py",
            "examples/passports/vectors.json",
        }
        self.assertEqual(set(report["source_sha256"]), paths)
        for name in paths:
            self.assertEqual(
                report["source_sha256"][name],
                hashlib.sha256((root / name).read_bytes()).hexdigest(),
            )

    def test_malformed_comparison_emits_no_evidence(self):
        changes = [
            ("crypto_accepts", [1, 1, 1, 1, 0, 1]),
            ("crypto_accepts", [1.0, 1.0, 1.0, 1.0, 0.0, 1.0]),
            ("hash_1mib_ms", True),
            ("hash_1mib_ms", -1),
            ("hash_1mib_ms", "fast"),
            ("hash_1mib_ms", float("nan")),
            ("hash_1mib_ms", float("inf")),
            ("duplicate_keys_collapsed", 1),
            ("duplicate_keys_collapsed", False),
            ("float_lexemes_collapsed", False),
            ("node", None),
            ("node", "v22.0.0\\nforged"),
            ("unexpected", "unreviewed"),
        ]
        samples = [
            (field + repr(value), json.dumps(self.response | {field: value}).encode())
            for field, value in changes
        ]
        raw = json.dumps(self.response).encode()
        samples.extend(
            [
                ("duplicate", b'{"node":"wrong",' + raw[1:]),
                (
                    "missing",
                    json.dumps(
                        {k: v for k, v in self.response.items() if k != "float_lexemes_collapsed"}
                    ).encode(),
                ),
                ("oversize", raw + b" " * 4096),
                ("overflow", raw.replace(b"1.25", b"1e999")),
            ]
        )
        for name, raw in samples:
            with self.subTest(name=name):
                output = io.StringIO()
                with self.assertRaises(ValueError):
                    self.invoke(raw, output)
                self.assertEqual(output.getvalue(), "")


class ProbeCaptureTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.capture = runpy.run_path(str(root / "scripts/passport_technology_probe.py"))[
            "_capture"
        ]

    def child(self, code, payload=b"", timeout=3):
        return self.capture([sys.executable, "-I", "-c", code], payload, timeout=timeout)

    def test_exact_limit_and_input_round_trip(self):
        self.assertEqual(
            self.child("import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())", b"a" * 4096),
            b"a" * 4096,
        )

    def test_each_output_stream_is_capped(self):
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream):
                with self.assertRaisesRegex(RuntimeError, "comparison_output_limit"):
                    self.child(f"import sys; sys.{stream}.buffer.write(b'x' * 4097)")

    def test_nonzero_exit_discards_success_shaped_output(self):
        with self.assertRaises(Exception) as failed:
            self.child("import sys; print('{}'); sys.exit(7)")
        self.assertIsInstance(failed.exception, RuntimeError)
        self.assertEqual(str(failed.exception), "comparison_exit")

    def test_timeout_does_not_return_partial_output(self):
        transports = []
        launch = asyncio.BaseEventLoop.subprocess_exec

        async def observed(loop, *args, **kwargs):
            result = await launch(loop, *args, **kwargs)
            transports.append(result[0])
            return result

        with patch.object(asyncio.BaseEventLoop, "subprocess_exec", observed):
            with self.assertRaises(Exception) as failed:
                self.child("import time; print('{}', flush=True); time.sleep(2)", timeout=0.2)
        self.assertIsInstance(failed.exception, RuntimeError)
        self.assertEqual(str(failed.exception), "comparison_timeout")
        self.assertEqual(len(transports), 1)
        self.assertIsNotNone(transports[0].get_returncode())
        self.assertTrue(transports[0].is_closing())

    def test_oversize_input_rejected_before_launch(self):
        with patch("asyncio.run") as launch:
            with self.assertRaisesRegex(ValueError, "comparison_input_size"):
                self.capture([sys.executable], b"a" * 65537)
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
