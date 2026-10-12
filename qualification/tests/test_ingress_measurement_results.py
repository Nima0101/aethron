"""Ingress timing evidence requires the actual measured declaration results."""

import contextlib
import io
import tempfile
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch

from qualification.technology import compare_ingress
from qualification.tests import test_audit_reports


class IngressMeasurementResultTests(unittest.TestCase):
    def reject_changed_result(self, path, value, at_call):
        fixture = test_audit_reports.AuditReportTests()
        lines = fixture.lines(fixture.responses())
        original = compare_ingress.validate
        measured_calls = 0

        def changed(raw, **kwargs):
            nonlocal measured_calls
            report = original(raw, **kwargs)
            if len(raw) == 65536:
                measured_calls += 1
                if measured_calls == at_call:
                    parent = report
                    for key in path[:-1]:
                        parent = parent[key]
                    parent[path[-1]] = value
            return report

        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            response = Path(directory) / "responses.jsonl"
            response.write_bytes(b"\n".join(lines) + b"\n")
            with (
                patch("sys.argv", ["compare_ingress", "--responses", str(response)]),
                patch.object(compare_ingress, "collect", return_value=[]),
                patch.object(compare_ingress, "validate", changed),
                contextlib.redirect_stdout(output),
            ):
                with self.assertRaisesRegex(RuntimeError, "^ingress_measurement_failed$"):
                    compare_ingress.main()
        self.assertEqual(measured_calls, at_call)
        self.assertEqual(output.getvalue(), "")
        self.assertFalse(tracemalloc.is_tracing())

    def test_complete_exact_result_required_for_timed_and_traced_calls(self):
        for at_call in (1, 21):
            for path, value in (
                (("declaration_checks_passed",), False),
                (("version",), True),
                (("sensor_count",), 2.0),
                (("record_count",), 0),
                (("evidence_counts", "synthetic"), 0),
                (("findings",), ["capture_stale"]),
                (("findings",), ()),
                (("artifacts_verified",), True),
                (("physical_qualification_passed",), 0),
                (("physical_status",), "passed"),
                (("input_sha256",), "0" * 64),
                (("unexpected",), "PRIVATE_MARKER"),
            ):
                with self.subTest(call=at_call, path=path):
                    self.reject_changed_result(path, value, at_call)

    def test_each_single_timed_failure_prevents_report(self):
        for at_call in range(2, 21):
            with self.subTest(call=at_call):
                self.reject_changed_result(("record_count",), 0, at_call)

    def test_real_measurement_preserves_scope(self):
        fixture = test_audit_reports.AuditReportTests()
        status, report = fixture.compare(fixture.lines(fixture.responses()))
        self.assertEqual(status, 0)
        measurement = report["python_65536_byte_measurement"]
        self.assertEqual(measurement["iterations"], 20)
        self.assertEqual(len(measurement["elapsed_ns"]), 20)
        self.assertIsNone(measurement["acceptance_threshold"])
        self.assertIs(report["physical_qualification_passed"], False)
        self.assertFalse(tracemalloc.is_tracing())


if __name__ == "__main__":
    unittest.main()
