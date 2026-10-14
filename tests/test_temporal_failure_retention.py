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
                self.assertFalse((output / "temporal-evaluation.json").exists())

    def test_retry_and_success_preserve_each_failed_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, _, _ = self.invoke(root, "clean")
            original = {p.name: p.read_bytes() for p in output.iterdir()}
            self.assertEqual(len(original), 1)
            self.invoke(root, "clean")
            failures = {p.name: p.read_bytes() for p in output.iterdir()}
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
