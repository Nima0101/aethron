"""Bounded audit harness checks; no network, vehicle, or simulator access."""

import importlib.util
import json

# Fixed local fixture processes, never caller-provided commands.
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class WireAuditTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[2] / "scripts/robotics_wire_audit_v2.py"
        self.assertTrue(path.is_file(), "missing executable technology comparison")
        spec = importlib.util.spec_from_file_location("wire_audit", path)
        self.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.api)

    def test_corpus_covers_both_layouts_and_wire_rejections(self):
        cases = self.api.corpus()
        self.assertGreaterEqual(len(cases), 12)
        self.assertLessEqual(len(cases), 32)
        self.assertEqual(len({case["name"] for case in cases}), len(cases))
        for case in cases:
            with self.subTest(name=case["name"]):
                result = self.api.python_result(bytes.fromhex(case["hex"]))
                self.assertEqual(result["accepted"], case["accepted"])
        self.assertEqual({case["message"] for case in cases if case["accepted"]}, {30, 32})

    def test_parity_rejects_disagreeing_admission_or_numeric_values(self):
        expected = [{"accepted": True, "message": 30, "boot": 10, "values": [0.1] * 6}]
        self.api.check_parity(expected, expected)
        for wrong in ([{"accepted": False}], [], [dict(expected[0], values=[1.0] * 6)]):
            with self.assertRaisesRegex(ValueError, "candidate_parity_failed"):
                self.api.check_parity(expected, wrong)

    def test_existing_output_is_refused_before_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "result.json").write_text("prior negative evidence")
            with self.assertRaises(FileExistsError):
                self.api.run(out)
            self.assertEqual((out / "result.json").read_text(), "prior negative evidence")

    def test_parity_rejects_boolean_numeric_substitution(self):
        expected = {"accepted": True, "message": 30, "boot": 0, "values": [0.0] * 6}
        for field, value in (
            ("accepted", 1),
            ("accepted", 1.0),
            ("boot", False),
            ("values", [False] * 6),
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(ValueError, "candidate_parity_failed"):
                    self.api.check_parity([expected], [dict(expected, **{field: value})])
        with self.assertRaisesRegex(ValueError, "candidate_parity_failed"):
            self.api.check_parity([{"accepted": False}], [{"accepted": 0}])

    def test_parity_requires_integer_metadata_and_preserves_finite_numeric_values(self):
        expected = {"accepted": True, "message": 30, "boot": 10, "values": [1.0] * 6}
        self.api.check_parity([expected], [dict(expected, values=[1] * 6)])
        for field, value in (("message", 30.0), ("boot", 10.0)):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "candidate_parity_failed"):
                    self.api.check_parity([expected], [dict(expected, **{field: value})])
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(nonfinite=value):
                with self.assertRaisesRegex(ValueError, "candidate_parity_failed"):
                    self.api.check_parity([expected], [dict(expected, values=[value] * 6)])

    def test_run_rejects_ambiguous_or_nonfinite_candidate_json(self):
        results = json.dumps(
            [self.api.python_result(bytes.fromhex(c["hex"])) for c in self.api.corpus()]
        )
        for fragment, reason in (
            ('"results": [], "benchmark": {"samples": 512},', "duplicate_json_member"),
            ('"benchmark": {"samples": 1, "samples": 512},', "duplicate_json_member"),
            ('"benchmark": {"p95_ns": NaN},', "nonfinite_json_number"),
            ('"benchmark": {"p95_ns": Infinity},', "nonfinite_json_number"),
            ('"benchmark": {"p95_ns": 1e999},', "nonfinite_json_number"),
        ):
            payload = "{" + fragment + '"results":' + results + "}"

            def execute(command, *, payload=payload, **kwargs):
                return "fixture compiler" if command[0] == "cc" else payload

            with self.subTest(fragment=fragment), tempfile.TemporaryDirectory() as directory:
                out = Path(directory) / "attempt"
                # Isolate JSON admission from code generation/compiler execution.
                with patch("pymavlink.generator.mavgen.mavgen", return_value=True):
                    with patch.object(self.api, "_execute", side_effect=execute):
                        with self.assertRaisesRegex(ValueError, reason):
                            self.api.run(out)
                self.assertEqual(json.loads((out / "result.json").read_text())["state"], "failed")

    def test_run_retains_compiler_timeout_bytes_and_failed_receipt(self):
        failure = subprocess.TimeoutExpired(
            "fixed compiler", 30, output=b"partial\xff\r\n", stderr=b"diagnostic\x00\r\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "attempt"
            with patch("pymavlink.generator.mavgen.mavgen", return_value=True):
                with patch.object(self.api.subprocess, "run", side_effect=failure):
                    with self.assertRaises(subprocess.TimeoutExpired) as caught:
                        self.api.run(out)
            self.assertIs(caught.exception, failure)
            self.assertTrue((out / "compiler-stdout.log").is_file(), "missing timeout stdout")
            self.assertEqual((out / "compiler-stdout.log").read_bytes(), failure.stdout)
            self.assertEqual((out / "compiler-stderr.log").read_bytes(), failure.stderr)
            report = json.loads((out / "result.json").read_text())
            self.assertEqual(report["state"], "failed")
            self.assertEqual(report["failure_type"], "TimeoutExpired")
            self.assertEqual(report["failed_stage"], "compiler")

    def test_run_retains_real_nonzero_compiler_output(self):
        real_run = subprocess.run

        def fail_compiler(command, **kwargs):
            program = "import sys; sys.stdout.buffer.write(b'partial\\r\\n'); sys.stderr.buffer.write(b'failure\\x00'); sys.exit(7)"
            return real_run([sys.executable, "-c", program], **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "attempt"
            with patch("pymavlink.generator.mavgen.mavgen", return_value=True):
                with patch.object(self.api.subprocess, "run", side_effect=fail_compiler):
                    with self.assertRaises(subprocess.CalledProcessError):
                        self.api.run(out)
            self.assertTrue((out / "compiler-stdout.log").is_file(), "missing failed stdout")
            self.assertEqual((out / "compiler-stdout.log").read_bytes(), b"partial\r\n")
            self.assertEqual((out / "compiler-stderr.log").read_bytes(), b"failure\x00")
            report = json.loads((out / "result.json").read_text())
            self.assertEqual(report["state"], "failed")
            self.assertEqual(report["failure_type"], "CalledProcessError")

    def test_rejected_json_and_utf8_preserve_successful_child_bytes(self):
        for raw in (b'{"results": [], "results": []}\r\n', b"invalid\xff\r\n"):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                out = Path(directory)
                program = "import sys; sys.stdout.buffer.write(bytes.fromhex(sys.argv[1])); sys.stderr.buffer.write(b'diagnostic\\x00')"
                with self.assertRaises(ValueError):
                    self.api.decode_candidate(
                        self.api._execute(
                            [sys.executable, "-c", program, raw.hex()],
                            timeout=5,
                            out=out,
                            label="candidate",
                        )
                    )
                self.assertEqual((out / "candidate-stdout.log").read_bytes(), raw)
                self.assertEqual((out / "candidate-stderr.log").read_bytes(), b"diagnostic\x00")

    def test_run_rejects_inconsistent_benchmark_metadata_in_both_profiles(self):
        results = [self.api.python_result(bytes.fromhex(c["hex"])) for c in self.api.corpus()]
        accepted = sum(results[i % len(results)]["accepted"] for i in range(512))
        valid = {"samples": 512, "accepted": accepted, "p50_ns": 1, "p95_ns": 2, "max_ns": 3}
        negatives = [
            None,
            {},
            dict(valid, extra=0),
            dict(valid, samples=511),
            dict(valid, accepted=accepted - 1),
            dict(valid, p50_ns=False),
            dict(valid, p95_ns=2.0),
            dict(valid, max_ns=-1),
            dict(valid, p50_ns=3),
            dict(valid, max_ns=1),
            dict(valid, max_ns=2**64),
        ]
        cases = [("candidate", value) for value in negatives]
        cases.append(("sanitized-candidate", dict(valid, accepted=accepted - 1)))
        for stage, invalid in cases:

            def execute(command, *, label, stage=stage, invalid=invalid, **kwargs):
                if command[0] == "cc":
                    return "fixture compiler"
                benchmark = invalid if label == stage else valid
                return json.dumps({"results": results, "benchmark": benchmark})

            with (
                self.subTest(stage=stage, invalid=invalid),
                tempfile.TemporaryDirectory() as directory,
            ):
                out = Path(directory) / "attempt"
                with patch("pymavlink.generator.mavgen.mavgen", return_value=True):
                    with patch.object(self.api, "_execute", side_effect=execute):
                        with self.assertRaisesRegex(ValueError, "candidate_benchmark_failed"):
                            self.api.run(out)
                report = json.loads((out / "result.json").read_text())
                self.assertEqual(report["state"], "failed")
                self.assertEqual(report["failed_stage"], stage)

    def test_run_preserves_valid_zero_resolution_timing_metadata(self):
        results = [self.api.python_result(bytes.fromhex(c["hex"])) for c in self.api.corpus()]
        accepted = sum(results[i % len(results)]["accepted"] for i in range(512))
        benchmark = {"samples": 512, "accepted": accepted, "p50_ns": 0, "p95_ns": 0, "max_ns": 0}

        def execute(command, **kwargs):
            if command[0] == "cc":
                return "fixture compiler"
            return json.dumps({"results": results, "benchmark": benchmark})

        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "attempt"
            with patch("pymavlink.generator.mavgen.mavgen", return_value=True):
                with patch.object(self.api, "_execute", side_effect=execute):
                    report = self.api.run(out)
            self.assertEqual(report["state"], "compared")
            self.assertEqual(report["c"], benchmark)
            self.assertNotIn("failed_stage", report)


if __name__ == "__main__":
    unittest.main()
