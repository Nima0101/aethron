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
        self.assertEqual(
            first["case_stream_sha256"],
            "6e88f2cf0402bbec11447de77c3cfa5f950acccce6935e54d0fa6ccfb6fecd07",
        )
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

    def test_report_mode_real_apis_reproducible_with_owned_fixture_cleanup(self):
        api = self.api()
        original = api.run_proposals
        paths, reports = [], []

        def observe(*args, **kwargs):
            paths.append(Path(args[1]))
            self.assertTrue(paths[-1].is_dir())
            value = original(*args, **kwargs)
            reports.append(value)
            return value

        with patch.object(api, "run_proposals", observe):
            first = api.run(cases=90, seconds=60, seed=123, reports=True)
        second = api.run(cases=90, seconds=60, seed=123, reports=True)
        self.assertTrue(first["all_succeeded"], first["failure"])
        self.assertEqual(first["version"], 2)
        self.assertEqual(
            first["case_stream_sha256"],
            "dc095c5fbe4692a7d5075773f689e7a7af906704be1102347d83af58a20620b2",
        )
        self.assertEqual(first["case_stream_sha256"], second["case_stream_sha256"])
        self.assertEqual(first["counts"], second["counts"])
        self.assertEqual(
            set(first["counts"]), {"report_annotations", "report_pin", "report_source"}
        )
        for row in first["counts"].values():
            self.assertEqual(row["accepted"] + row["rejected"], 30)
            self.assertEqual(row["controls"], 6)
            self.assertGreater(row["rejected"], 0)
        self.assertEqual(len(paths), 90)
        self.assertTrue(all(not path.exists() for path in paths))
        for report in reports[0]["reports"]:
            groups = report["metrics_by_provenance"]
            self.assertEqual(len(groups), 2)  # Third source only supplies train/validation.
            self.assertEqual(sum(g["frames"] for g in groups.values()), 3)
            for key in ("true_positives", "false_positives", "false_negatives"):
                self.assertEqual(sum(g[key] for g in groups.values()), report["metrics"][key])
        self.assertNotIn(str(paths[0]), json.dumps(first))
        self.assertFalse(first["qualified"])

    def test_report_oracle_rejects_bad_totals_extra_sources_and_private_fields(self):
        api = self.api()
        original = api.run_proposals
        for corruption in ("totals", "source", "private", "ratio"):

            def corrupt(*args, corruption=corruption, **kwargs):
                value = original(*args, **kwargs)
                report = value["reports"][0]
                groups = report["metrics_by_provenance"]
                if corruption == "source":
                    groups["0" * 64] = next(iter(groups.values())).copy()
                elif corruption == "private":
                    report["private"] = "private payload"
                elif corruption == "ratio":
                    next(iter(groups.values()))["precision"] = True
                else:
                    report["metrics"]["true_positives"] += 1
                return value

            with self.subTest(corruption=corruption), patch.object(api, "run_proposals", corrupt):
                result = api.run(cases=3, seconds=60, reports=True)
                self.assertFalse(result["all_succeeded"])
                self.assertEqual(result["failure"]["reason"], "unexpected_result")
                self.assertEqual(result["cases"], 1)
                self.assertNotIn("private", json.dumps(result))

    def test_report_errors_are_sanitized_and_source_binding_loss_retains_counts(self):
        api = self.api()
        for error in (ValueError("invalid_annotations"), OSError("private path")):
            with patch.object(api, "run_proposals", side_effect=error):
                result = api.run(cases=3, seconds=60, reports=True)
            self.assertFalse(result["all_succeeded"])
            self.assertEqual(result["cases"], 1)
            self.assertNotIn("private", json.dumps(result))
        sources = api._sources()
        with patch.object(api, "_sources", side_effect=[sources, OSError("private path")]):
            result = api.run(cases=3, seconds=60, reports=True)
        self.assertEqual(result["cases"], 3)
        self.assertFalse(result["source_stable"])
        self.assertFalse(result["all_succeeded"])

    def test_report_cli_and_strict_option(self):
        api = self.api()
        for value in (None, 1, "true"):
            with self.assertRaisesRegex(ValueError, "^invalid_fuzz_input$"):
                api.run(reports=value)
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["dataset_fuzz", "--reports", "--cases", "3"]),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(api.main(), 0)
        self.assertEqual(json.loads(output.getvalue())["version"], 2)

    def test_report_deadline_cleans_fixture_and_never_claims_success(self):
        api = self.api()
        now, paths = [0], []
        original = api.run_proposals

        def slow(*args, **kwargs):
            paths.append(Path(args[1]))
            result = original(*args, **kwargs)
            now[0] = 2
            return result

        with (
            patch.object(api, "run_proposals", slow),
            patch.object(api.time, "monotonic", lambda: now[0]),
        ):
            result = api.run(cases=1, seconds=1, reports=True)
        self.assertEqual(result["cases"], 1)
        self.assertEqual(result["status"], "time_limit")
        self.assertFalse(result["all_succeeded"])
        self.assertTrue(paths)
        self.assertTrue(all(not p.exists() for p in paths))

    def test_owned_fixture_setup_failure_is_sanitized(self):
        api = self.api()
        with patch.object(api.tempfile, "TemporaryDirectory", side_effect=OSError("private path")):
            for reports in (False, True):
                with self.assertRaisesRegex(ValueError, "^invalid_fuzz_input$"):
                    api.run(reports=reports)

    def test_owned_fixture_cleanup_failure_is_sanitized(self):
        api = self.api()
        original = api.tempfile.TemporaryDirectory

        @contextlib.contextmanager
        def failed_cleanup(*args, **kwargs):
            with original(*args, **kwargs) as directory:
                yield directory
            raise OSError("private cleanup path")

        with patch.object(api.tempfile, "TemporaryDirectory", failed_cleanup):
            for reports in (False, True):
                with self.assertRaisesRegex(ValueError, "^invalid_fuzz_input$"):
                    api.run(cases=3, reports=reports)

    def test_report_mutations_reach_valid_changed_annotation_metrics(self):
        api = self.api()
        original, observed = api.run_proposals, set()

        def observe(*args, **kwargs):
            result = original(*args, **kwargs)
            metrics = result["reports"][0]["metrics"]
            observed.add(
                tuple(metrics[k] for k in ("true_positives", "false_positives", "false_negatives"))
            )
            return result

        with patch.object(api, "run_proposals", observe):
            result = api.run(cases=90, seconds=60, reports=True, seed=123)
        self.assertTrue(result["all_succeeded"], result["failure"])
        row = result["counts"]["report_annotations"]
        self.assertEqual(row, {"accepted": 12, "rejected": 18, "controls": 6})
        self.assertTrue({(0, 1, 0), (0, 1, 3), (1, 0, 4)}.issubset(observed), observed)

    def test_candidate_mode_runs_real_verifier_and_sparse_budget_rejections(self):
        api = self.api()
        original, paths, sizes = api.verify_candidate, [], []

        def safe_observe(data, manifest, root, **pins):
            paths.append(Path(root))
            try:
                reference = json.loads(data)["artifact_sha256"]
            except (ValueError, TypeError, KeyError, UnicodeError):
                reference = None
            for path in Path(root).iterdir():
                if path.name == reference:
                    sizes.append(path.stat().st_size)
            return original(data, manifest, root, **pins)

        with patch.object(api, "verify_candidate", safe_observe):
            first = api.run(cases=90, seconds=60, seed=123, candidates=True)
        second = api.run(cases=90, seconds=60, seed=123, candidates=True)
        self.assertTrue(first["all_succeeded"], first["failure"])
        self.assertEqual(first["version"], 3)
        self.assertEqual(first["case_stream_sha256"], second["case_stream_sha256"])
        self.assertEqual(first["counts"], second["counts"])
        self.assertEqual(
            set(first["counts"]), {"candidate_descriptor", "candidate_pin", "candidate_artifact"}
        )
        for counts in first["counts"].values():
            self.assertEqual(counts["accepted"] + counts["rejected"], 30)
            self.assertEqual(counts["controls"], 6)
            self.assertGreater(counts["rejected"], 0)
        self.assertIn(64 * 1024 * 1024 + 1, sizes)
        self.assertTrue(paths)
        self.assertTrue(all(not p.exists() for p in paths))
        self.assertNotIn(str(paths[0]), json.dumps(first))

    def test_candidate_failures_and_false_qualification_are_sanitized(self):
        api = self.api()
        for error in (ValueError("invalid_model_candidate"), OSError("private path")):
            with patch.object(api, "verify_candidate", side_effect=error):
                result = api.run(cases=3, seconds=60, candidates=True)
            self.assertFalse(result["all_succeeded"])
            self.assertEqual(result["cases"], 1)
            self.assertNotIn("private", json.dumps(result))
        original = api.verify_candidate

        def corrupt(*args, **kwargs):
            value = original(*args, **kwargs)
            value["qualified"] = True
            value["private"] = "private payload"
            return value

        with patch.object(api, "verify_candidate", corrupt):
            result = api.run(cases=3, candidates=True)
        self.assertEqual(result["failure"]["reason"], "unexpected_result")
        self.assertNotIn("private", json.dumps(result))

    def test_candidate_mode_cli_selection_and_deadline(self):
        api = self.api()
        for changes in (
            {"candidates": 1},
            {"candidates": None},
            {"candidates": True, "reports": True},
        ):
            with self.assertRaisesRegex(ValueError, "^invalid_fuzz_input$"):
                api.run(**changes)
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["dataset_fuzz", "--candidates", "--cases", "3"]),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(api.main(), 0)
        self.assertEqual(json.loads(output.getvalue())["version"], 3)
        with patch.object(api.time, "monotonic", side_effect=[0, 2, 2]):
            result = api.run(cases=3, seconds=1, candidates=True)
        self.assertEqual(result["cases"], 0)
        self.assertEqual(result["status"], "time_limit")
        self.assertFalse(result["all_succeeded"])
