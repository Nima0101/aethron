"""Fuzz-driver regressions: real APIs, bounded work and honest failure reports."""

import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dataset_fuzz.py"


class DatasetFuzz(unittest.TestCase):
    def api(self):
        self.assertTrue(SCRIPT.is_file(), "dataset fuzz harness is missing")
        spec = importlib.util.spec_from_file_location("dataset_fuzz", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_seeded_cases_are_reproducible_and_exercise_each_api(self):
        api = self.api()
        first = api.run(cases=90, seconds=60, seed=123)
        second = api.run(cases=90, seconds=60, seed=123)
        self.assertTrue(first["all_succeeded"])
        self.assertFalse(first["qualified"])
        self.assertEqual(first["cases"], 90)
        self.assertEqual(first["case_stream_sha256"], second["case_stream_sha256"])
        self.assertEqual(first["counts"], second["counts"])
        for row in first["counts"].values():
            self.assertEqual(row["accepted"] + row["rejected"], 30)
            self.assertEqual(row["controls"], 6)
            self.assertGreater(row["rejected"], 0)
        self.assertNotEqual(
            first["case_stream_sha256"],
            api.run(cases=90, seconds=60, seed=124)["case_stream_sha256"],
        )

    def test_invalid_budgets_reject(self):
        api = self.api()
        for changes in (
            {"cases": 0},
            {"cases": 10001},
            {"cases": True},
            {"seconds": 0},
            {"seconds": 61},
            {"seconds": float("nan")},
            {"seed": -1},
            {"seed": True},
            {"seed": 2**32},
        ):
            with (
                self.subTest(changes=changes),
                self.assertRaisesRegex(ValueError, "^invalid_fuzz_input$"),
            ):
                api.run(**changes)

    def test_deadline_and_overrun_cannot_report_completed_success(self):
        api = self.api()
        with patch.object(api.time, "monotonic", side_effect=[0, 2, 2]):
            result = api.run(cases=9, seconds=1)
        self.assertEqual(result["status"], "time_limit")
        self.assertEqual(result["cases"], 0)
        self.assertFalse(result["all_succeeded"])
        now = [0]
        original = api.validate_manifest

        def slow(data):
            result = original(data)
            now[0] = 2
            return result

        with (
            patch.object(api.time, "monotonic", lambda: now[0]),
            patch.object(api, "validate_manifest", slow),
        ):
            result = api.run(cases=1, seconds=1)
        self.assertEqual(result["cases"], 1)
        self.assertEqual(result["status"], "time_limit")
        self.assertFalse(result["all_succeeded"])

    def test_unexpected_exception_is_sanitized_and_cli_fails(self):
        api = self.api()
        output = io.StringIO()
        with (
            patch.object(api, "validate_manifest", side_effect=RuntimeError("private payload")),
            patch.object(sys, "argv", ["dataset_fuzz", "--cases", "9"]),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(api.main(), 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["cases"], 1)
        self.assertEqual(result["failure"]["index"], 0)
        self.assertEqual(result["failure"]["target"], "manifest")
        self.assertEqual(len(result["failure"]["sha256"]), 64)
        self.assertNotIn("private", output.getvalue())
        self.assertFalse(result["all_succeeded"])

    def test_valid_control_rejection_and_bad_results_are_failures(self):
        api = self.api()
        for replacement in (ValueError("invalid_split_manifest"), ValueError("private error")):
            with patch.object(api, "validate_manifest", side_effect=replacement):
                result = api.run(cases=3, seconds=60)
            self.assertFalse(result["all_succeeded"])
            self.assertEqual(result["cases"], 1)
            self.assertNotIn("private", json.dumps(result))
        with patch.object(api, "validate_manifest", return_value={}):
            result = api.run(cases=3, seconds=60)
        self.assertFalse(result["all_succeeded"])

    def test_lost_source_binding_preserves_case_counts(self):
        api = self.api()
        sources = api._sources()
        with patch.object(api, "_sources", side_effect=[sources, OSError("private path")]):
            result = api.run(cases=3, seconds=60)
        self.assertEqual(result["cases"], 3)
        self.assertFalse(result["source_stable"])
        self.assertFalse(result["all_succeeded"])
