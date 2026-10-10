"""Binding measurements must reject incorrect workload results before output."""

import contextlib
import io
import json
import tracemalloc
import unittest
from unittest.mock import patch

from qualification.technology import measure_binding


class BindingMeasurementResultTests(unittest.TestCase):
    def reject_changed_result(self, path, value, *, traced, at_call=None):
        original = measure_binding.verify
        calls = 0

        def changed(*args, **kwargs):
            nonlocal calls
            calls += 1
            report = original(*args, **kwargs)
            if tracemalloc.is_tracing() is traced and (at_call is None or calls == at_call):
                parent = report
                for key in path[:-1]:
                    parent = parent[key]
                parent[path[-1]] = value
            return report

        output = io.StringIO()
        with patch.object(measure_binding, "verify", changed), contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "^binding_measurement_failed$"):
                measure_binding.main()
        self.assertEqual(output.getvalue(), "")
        self.assertFalse(tracemalloc.is_tracing())

    def test_timed_results_require_complete_exact_report(self):
        cases = (
            (("software_checks_passed",), False),
            (("artifact_authenticity_verified",), True),
            (("artifact_bytes_verified",), 1),
            (("physical_qualification_passed",), 0),
            (("artifact_counts", "matched"), 3),
            (("artifact_counts", "matched"), 4.0),
            (("artifact_counts", "missing"), False),
            (("artifact_counts", "supplied_bytes"), 0),
            (("artifact_findings",), ["artifact_missing"]),
            (("artifact_findings",), ()),
            (("declaration", "declaration_checks_passed"), False),
            (("declaration", "input_sha256"), "0" * 64),
            (("declaration", "physical_qualification_passed"), True),
            (("declaration", "evidence_counts", "synthetic"), 0),
            (("declaration", "findings"), ["capture_stale"]),
            (("declaration",), {}),
            (("unexpected_field",), "PRIVATE_MARKER"),
        )
        for path, value in cases:
            with self.subTest(path=path, value=value):
                self.reject_changed_result(path, value, traced=False)

    def test_traced_result_is_checked_and_trace_released(self):
        for path, value in (
            (("artifact_bytes_verified",), False),
            (("physical_qualification_passed",), True),
            (("artifact_counts", "matched"), 0),
            (("declaration", "findings"), ["capture_stale"]),
        ):
            with self.subTest(path=path):
                self.reject_changed_result(path, value, traced=True)

    def test_failure_in_any_single_timed_call_prevents_report(self):
        for call in range(1, 11):
            with self.subTest(call=call):
                self.reject_changed_result(
                    ("artifact_counts", "matched"), 0, traced=False, at_call=call
                )

    def test_real_measurement_preserves_four_mib_scope(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            measure_binding.main()
        report = json.loads(output.getvalue())
        self.assertEqual(
            report["artifact_counts"],
            {
                "referenced": 4,
                "supplied": 4,
                "matched": 4,
                "missing": 0,
                "mismatched": 0,
                "unreferenced": 0,
                "supplied_bytes": 4194304,
            },
        )
        self.assertEqual(len(report["verify_elapsed_ns"]), 10)
        self.assertIs(report["physical_qualification_passed"], False)
        self.assertFalse(tracemalloc.is_tracing())
