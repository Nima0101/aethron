"""Evidence checks must survive interpreter optimization; no model execution."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import temporal_evaluate as temporal


class TemporalEvaluationGates(unittest.TestCase):
    def setUp(self):
        # These isolated gate tests supply partial inert datasets deliberately.
        inventory = patch.object(
            temporal,
            "synthetic_fixture_paths",
            side_effect=lambda: sorted((temporal.ROOT / "data/temporal").glob("*.json")),
        )
        inventory.start()
        self.addCleanup(inventory.stop)

    def test_replay_mismatch_is_rejected(self):
        with patch.object(temporal, "replay", side_effect=([{"a": 1}], [{"a": 2}])):
            with self.assertRaisesRegex(AssertionError, "nondeterministic replay"):
                temporal.outputs([])
        with patch.object(temporal, "replay", return_value=[]):
            self.assertEqual(temporal.outputs([]), ([], []))

    def test_digest_mismatch_is_rejected_before_detector(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data/aot"
            data.mkdir(parents=True)
            (data / "sample.pgm").write_bytes(b"synthetic-invalid-digest")
            (data / "manifest.json").write_text(
                json.dumps({"frames": [{"file": "sample.pgm", "sha256": "0" * 64}]})
            )
            with (
                patch.object(temporal, "ROOT", root),
                patch.object(
                    temporal, "detect_pgm", side_effect=RuntimeError("detector_called")
                ) as detector,
            ):
                caught = None
                try:
                    temporal.recorded(root)
                except Exception as error:
                    caught = error
                self.assertIsInstance(caught, AssertionError)
                detector.assert_not_called()
                (data / "manifest.json").write_text(
                    json.dumps(
                        {
                            "frames": [
                                {
                                    "file": "sample.pgm",
                                    "sha256": hashlib.sha256(
                                        (data / "sample.pgm").read_bytes()
                                    ).hexdigest(),
                                }
                            ]
                        }
                    )
                )
                with self.assertRaisesRegex(RuntimeError, "detector_called"):
                    temporal.recorded(root)
                detector.assert_called_once_with(b"synthetic-invalid-digest")

    def test_incomplete_benchmark_output_is_rejected(self):
        model = Mock()
        model.step.return_value = {"tracks": []}
        with patch.object(temporal, "Session", return_value=model) as factory:
            with self.assertRaises(AssertionError):
                temporal.benchmark()
            factory.assert_called_once_with()
            model.close.assert_called_once_with()

    def test_metric_and_budget_failures_cannot_be_removed(self):
        for case in ("fast_uav", "clean", "budget"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixtures = root / "data/temporal"
                fixtures.mkdir(parents=True)
                if case != "budget":
                    (fixtures / (case + ".json")).write_text("[]")
                with (
                    patch.object(temporal, "ROOT", root),
                    patch.object(temporal, "outputs", return_value=([], [])),
                    patch.object(
                        temporal,
                        "metrics",
                        side_effect=[
                            {"id_switches": 1, "recall": 0.89},
                            {"id_switches": 0, "recall": 1.0},
                        ],
                    ),
                    patch.object(temporal, "benchmark", return_value={"passed": case != "budget"}),
                    patch.object(temporal, "recorded") as recorded,
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    with self.assertRaises(AssertionError):
                        temporal.run(root / "output", include_recorded=False)
                    recorded.assert_not_called()
                if case == "budget":
                    # Failure evidence must still be written before raising.
                    report = json.loads((root / "output/temporal-evaluation.json").read_text())
                    self.assertIs(report["benchmark"]["passed"], False)
                    self.assertIs(report["passed"], False)
                    self.assertEqual(report["failure_stage"], "benchmark_gate")

    def test_interrupted_execution_retains_partial_report_and_original_error(self):
        for stage in ("benchmark", "recorded"):
            for error_type in (RuntimeError, KeyboardInterrupt):
                with self.subTest(stage=stage, error=error_type.__name__):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        fixtures = root / "data/temporal"
                        fixtures.mkdir(parents=True)
                        (fixtures / "clean.json").write_text("[]")
                        outdir = root / "output"
                        outdir.mkdir()
                        report_path = outdir / "temporal-evaluation.json"
                        report_path.write_text('{"passed": true, "stale": true}')
                        error = error_type("private_error_payload")
                        with (
                            patch.object(temporal, "ROOT", root),
                            patch.object(temporal, "outputs", return_value=([], [])),
                            patch.object(temporal, "metrics", return_value={"recall": 1.0}),
                            patch.object(temporal, "benchmark", return_value={"passed": True}),
                            patch.object(temporal, "recorded"),
                            patch.object(temporal, stage, side_effect=error),
                            contextlib.redirect_stdout(io.StringIO()),
                        ):
                            with self.assertRaises(error_type) as caught:
                                temporal.run(outdir)
                        self.assertIs(caught.exception, error)
                        report = json.loads(report_path.read_text())
                        self.assertIs(report["passed"], False)
                        self.assertEqual(report["failure_stage"], stage)
                        self.assertEqual(report["synthetic"]["clean"]["temporal"]["recall"], 1.0)
                        self.assertEqual("benchmark" in report, stage == "recorded")
                        self.assertNotIn("recorded", report)
                        self.assertNotIn("stale", report)
                        self.assertNotIn("private_error_payload", report_path.read_text())

    def test_successful_inert_gate_values_are_not_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = root / "data/temporal"
            fixtures.mkdir(parents=True)
            for name in ("fast_uav", "clean"):
                (fixtures / (name + ".json")).write_text("[]")
            with (
                patch.object(temporal, "ROOT", root),
                patch.object(temporal, "outputs", return_value=([], [])),
                patch.object(temporal, "metrics", return_value={"id_switches": 0, "recall": 1.0}),
                patch.object(temporal, "benchmark", return_value={"passed": True}),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                report = temporal.run(root / "output", include_recorded=False)
            self.assertIs(report["benchmark"]["passed"], True)
            self.assertIs(report["passed"], True)
            self.assertNotIn("failure_stage", report)


if __name__ == "__main__":
    unittest.main()
