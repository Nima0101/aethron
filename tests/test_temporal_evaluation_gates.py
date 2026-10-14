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


if __name__ == "__main__":
    unittest.main()
