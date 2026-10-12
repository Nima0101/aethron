"""Audit measurements must own tracing and preserve failures before reporting."""

import contextlib
import hashlib
import io
import json
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch

from qualification.technology import compare_campaign, compare_ingress, measure_binding
from qualification.tests import test_audit_reports

MODULES = (compare_ingress, measure_binding, compare_campaign)


class MeasurementReviewTests(unittest.TestCase):
    def invoke(self, module):
        if module is compare_ingress:
            fixture = test_audit_reports.AuditReportTests()
            status, report = fixture.compare(fixture.lines(fixture.responses()))
            self.assertEqual(status, 0)
            return report
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            module.main()
        return json.loads(output.getvalue())

    def test_active_caller_trace_is_rejected_and_preserved(self):
        self.assertFalse(tracemalloc.is_tracing())
        for module in MODULES:
            with self.subTest(module=module.__name__):
                tracemalloc.start()
                marker = bytearray(4096)
                before = tracemalloc.get_object_traceback(marker)
                self.assertIsNotNone(before)
                try:
                    with self.assertRaisesRegex(RuntimeError, "^audit_tracing_already_active$"):
                        self.invoke(module)
                    self.assertTrue(tracemalloc.is_tracing())
                    self.assertEqual(tracemalloc.get_object_traceback(marker), before)
                finally:
                    tracemalloc.stop()

    def test_peak_read_failure_stops_owned_tracing(self):
        for module in MODULES:
            with self.subTest(module=module.__name__):
                try:
                    with patch.object(
                        tracemalloc, "get_traced_memory", side_effect=RuntimeError("peak_failed")
                    ):
                        with self.assertRaisesRegex(RuntimeError, "^peak_failed$"):
                            self.invoke(module)
                    self.assertFalse(tracemalloc.is_tracing())
                finally:
                    tracemalloc.stop()

    def test_measured_function_failure_stops_owned_tracing(self):
        for module, name in (
            (compare_ingress, "validate"),
            (measure_binding, "verify"),
            (compare_campaign, "evaluate"),
        ):
            original = getattr(module, name)

            def fail_when_traced(*args, _original=original, **kwargs):
                if tracemalloc.is_tracing():
                    raise RuntimeError("measurement_failed")
                return _original(*args, **kwargs)

            with self.subTest(module=module.__name__):
                try:
                    with patch.object(module, name, fail_when_traced):
                        with self.assertRaisesRegex(RuntimeError, "^measurement_failed$"):
                            self.invoke(module)
                    self.assertFalse(tracemalloc.is_tracing())
                finally:
                    tracemalloc.stop()

    def test_success_reports_bind_current_measurement_source_and_policy(self):
        helper = "qualification/technology/measurement.py"
        for module in MODULES:
            with self.subTest(module=module.__name__):
                report = self.invoke(module)
                self.assertFalse(tracemalloc.is_tracing())
                self.assertEqual(report.get("audit_policy_version"), 3)
                self.assertIn(helper, report["source_sha256"])
                self.assertEqual(
                    report["source_sha256"][helper],
                    hashlib.sha256(Path(helper).read_bytes()).hexdigest(),
                )
                self.assertIs(report["physical_qualification_passed"], False)


if __name__ == "__main__":
    unittest.main()
