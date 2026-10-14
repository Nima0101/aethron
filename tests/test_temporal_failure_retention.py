"""Failure-report persistence with inert metrics; no performance qualification."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import temporal_evaluate as temporal


class TemporalFailureRetention(unittest.TestCase):
    def setUp(self):
        # Exercise report retention independently of the frozen inventory gate.
        inventory = patch.object(
            temporal,
            "synthetic_fixture_paths",
            side_effect=lambda: sorted((temporal.ROOT / "data/temporal").glob("*.json")),
        )
        inventory.start()
        self.addCleanup(inventory.stop)

    def invoke(self, root, name, *, passed=False):
        fixtures = root / "data/temporal"
        fixtures.mkdir(parents=True, exist_ok=True)
        (fixtures / (name + ".json")).write_bytes(b"[]\n")
        output = root / "output"
        measured = {"id_switches": 0 if passed else 2, "recall": 1.0 if passed else 0.89}
        baseline = {"id_switches": 1, "recall": 1.0}
        with (
            patch.object(temporal, "ROOT", root),
            patch.object(temporal, "outputs", return_value=([], [])),
            patch.object(temporal, "metrics", side_effect=[measured, baseline]),
            patch.object(temporal, "benchmark", return_value={"passed": True}) as benchmark,
            patch.object(temporal, "recorded") as recorded,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            if passed:
                temporal.run(output, include_recorded=False)
                benchmark.assert_called_once_with()
            else:
                with self.assertRaises(AssertionError):
                    temporal.run(output, include_recorded=False)
                benchmark.assert_not_called()
            recorded.assert_not_called()
        return output, measured, baseline

    def test_failed_metrics_are_retained_before_rejection(self):
        for name in ("fast_uav", "occlusion", "clean"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                output, measured, baseline = self.invoke(Path(directory), name)
                reports = list(output.glob("temporal-evaluation-failure-*.json"))
                self.assertEqual(len(reports), 1)
                report = json.loads(reports[0].read_bytes())
                self.assertIs(report["passed"], False)
                self.assertIs(report["complete"], False)
                self.assertEqual(report["fixture"], name)
                self.assertEqual(
                    report["gate"], "clean_recall" if name == "clean" else "id_switches"
                )
                self.assertEqual(report["metrics"], {"temporal": measured, "greedy_iou": baseline})
                self.assertEqual(report["fixture_sha256"], hashlib.sha256(b"[]\n").hexdigest())
                self.assertEqual(
                    report["evaluation_script_sha256"],
                    hashlib.sha256(Path(temporal.__file__).read_bytes()).hexdigest(),
                )
                self.assertNotIn("benchmark", report)
                latest = json.loads((output / "temporal-evaluation.json").read_bytes())
                self.assertIs(latest["passed"], False)
                self.assertEqual(latest["failure_stage"], "synthetic")
                self.assertEqual(latest["synthetic"][name], report["metrics"])
                self.assertNotIn("benchmark", latest)

    def test_retry_and_success_preserve_each_failed_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, _, _ = self.invoke(root, "clean")
            original = {
                p.name: p.read_bytes() for p in output.glob("temporal-evaluation-failure-*.json")
            }
            self.assertEqual(len(original), 1)
            self.invoke(root, "clean")
            failures = {
                p.name: p.read_bytes() for p in output.glob("temporal-evaluation-failure-*.json")
            }
            self.assertEqual(len(failures), 2)
            self.assertTrue(original.items() <= failures.items())
            self.invoke(root, "clean", passed=True)
            for name, data in failures.items():
                self.assertEqual((output / name).read_bytes(), data)
            self.assertIs(
                json.loads((output / "temporal-evaluation.json").read_bytes())["benchmark"][
                    "passed"
                ],
                True,
            )

    def test_passing_metrics_do_not_create_failure_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            output, _, _ = self.invoke(Path(directory), "clean", passed=True)
            self.assertEqual([p.name for p in output.iterdir()], ["temporal-evaluation.json"])

    def test_failed_metric_gate_replaces_a_previous_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, _, _ = self.invoke(root, "clean", passed=True)
            self.assertIs(
                json.loads((output / "temporal-evaluation.json").read_bytes())["passed"], True
            )
            self.invoke(root, "clean")
            report = json.loads((output / "temporal-evaluation.json").read_bytes())
            self.assertIs(report["passed"], False)
            self.assertEqual(report["failure_stage"], "synthetic")
            self.assertEqual(report["synthetic"]["clean"]["temporal"]["recall"], 0.89)
            self.assertNotIn("benchmark", report)
            self.assertEqual(len(list(output.glob("temporal-evaluation-failure-*.json"))), 1)

    def test_synthetic_interruptions_replace_stale_success_without_error_payloads(self):
        for operation in ("outputs", "metrics"):
            for error_type in (RuntimeError, KeyboardInterrupt):
                with self.subTest(operation=operation, error=error_type.__name__):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        fixtures = root / "data/temporal"
                        fixtures.mkdir(parents=True)
                        for name in ("a_completed", "b_interrupted"):
                            (fixtures / (name + ".json")).write_text("[]")
                        output = root / "output"
                        output.mkdir()
                        report_path = output / "temporal-evaluation.json"
                        report_path.write_text('{"passed": true, "stale": true}')
                        measured = {"recall": 1.0}
                        error = error_type("private_error_payload")
                        completed = [([], [])] if operation == "outputs" else [measured] * 2
                        with (
                            patch.object(temporal, "ROOT", root),
                            patch.object(temporal, "outputs", return_value=([], [])),
                            patch.object(temporal, "metrics", return_value=measured),
                            patch.object(temporal, operation, side_effect=[*completed, error]),
                            patch.object(temporal, "benchmark") as benchmark,
                            patch.object(temporal, "recorded") as recorded,
                        ):
                            with self.assertRaises(error_type) as caught:
                                temporal.run(output)
                        self.assertIs(caught.exception, error)
                        benchmark.assert_not_called()
                        recorded.assert_not_called()
                        report = json.loads(report_path.read_bytes())
                        self.assertIs(report["passed"], False)
                        self.assertEqual(report["failure_stage"], "synthetic")
                        self.assertEqual(
                            report["synthetic"],
                            {"a_completed": {"temporal": measured, "greedy_iou": measured}},
                        )
                        self.assertNotIn("benchmark", report)
                        self.assertNotIn("stale", report)
                        self.assertNotIn("private_error_payload", report_path.read_text())

    def test_invalid_fixture_replaces_stale_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = root / "data/temporal"
            fixtures.mkdir(parents=True)
            (fixtures / "clean.json").write_text("private_invalid_json")
            output = root / "output"
            output.mkdir()
            report_path = output / "temporal-evaluation.json"
            report_path.write_text('{"passed": true}')
            with (
                patch.object(temporal, "ROOT", root),
                patch.object(temporal, "outputs") as outputs,
                patch.object(temporal, "benchmark") as benchmark,
            ):
                with self.assertRaises(json.JSONDecodeError):
                    temporal.run(output)
            outputs.assert_not_called()
            benchmark.assert_not_called()
            report = json.loads(report_path.read_bytes())
            self.assertIs(report["passed"], False)
            self.assertEqual(report["failure_stage"], "synthetic")
            self.assertEqual(report["synthetic"], {})
            self.assertNotIn("private_invalid_json", report_path.read_text())
