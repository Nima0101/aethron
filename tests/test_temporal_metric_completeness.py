"""Evaluation evidence must account for every input and output frame."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import temporal_evaluate as temporal


class TemporalMetricCompleteness(unittest.TestCase):
    def setUp(self):
        # Exercise frame completeness with a small dataset, not the frozen corpus.
        inventory = patch.object(
            temporal,
            "synthetic_fixture_paths",
            side_effect=lambda: sorted((temporal.ROOT / "data/temporal").glob("*.json")),
        )
        inventory.start()
        self.addCleanup(inventory.stop)
        payload = patch.object(
            temporal, "synthetic_fixture_payload", side_effect=lambda path: path.read_bytes()
        )
        payload.start()
        self.addCleanup(payload.stop)
        self.truth = {"id": "fixture", "class": "obstacle", "box": [0.1, 0.1, 0.1, 0.1]}
        self.entry = {"truth": [self.truth]}
        self.result = {"tracks": [dict(self.truth, status="PRESENT")]}

    def test_missing_or_surplus_results_cannot_produce_metrics(self):
        for inputs, outputs in ((2, 1), (1, 2), (1, 0), (0, 1)):
            with self.subTest(inputs=inputs, outputs=outputs):
                with self.assertRaisesRegex(ValueError, "^evaluation_frame_count_mismatch$"):
                    temporal.metrics([self.entry] * inputs, [self.result] * outputs)

    def test_complete_results_count_misses_and_false_positives(self):
        report = temporal.metrics([self.entry] * 2, [self.result, {"tracks": []}])
        self.assertEqual(report["true_positives"], 1)
        self.assertEqual(report["false_negatives"], 1)
        self.assertEqual(report["recall"], 0.5)
        report = temporal.metrics([self.entry, {"truth": []}], [self.result] * 2)
        self.assertEqual(report["true_positives"], 1)
        self.assertEqual(report["false_positives"], 1)
        self.assertEqual(report["precision"], 0.5)

    def test_equal_empty_sequences_preserve_undefined_rates(self):
        report = temporal.metrics([], [])
        self.assertIsNone(report["recall"])
        self.assertIsNone(report["precision"])
        self.assertEqual(report["false_negatives"], 0)
        self.assertEqual(report["false_positives"], 0)

    def test_incomplete_temporal_or_baseline_cannot_publish_success(self):
        for branch in (0, 1):
            for count in (0, 1, 3):
                with self.subTest(branch=branch, count=count):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        fixtures = root / "data/temporal"
                        fixtures.mkdir(parents=True)
                        entries = [self.entry] * 2
                        (fixtures / "sequence.json").write_text(json.dumps(entries))
                        output = root / "output"
                        output.mkdir()
                        report_path = output / "temporal-evaluation.json"
                        report_path.write_text('{"passed": true, "stale": true}')
                        results = [[self.result] * 2, [self.result] * 2]
                        results[branch] = [self.result] * count
                        with (
                            patch.object(temporal, "ROOT", root),
                            patch.object(temporal, "outputs", return_value=results),
                            patch.object(
                                temporal, "benchmark", return_value={"passed": True}
                            ) as benchmark,
                            patch.object(temporal, "recorded", return_value={}) as recorded,
                            contextlib.redirect_stdout(io.StringIO()) as stdout,
                        ):
                            with self.assertRaisesRegex(
                                ValueError, "^evaluation_frame_count_mismatch$"
                            ):
                                temporal.run(output)
                        benchmark.assert_not_called()
                        recorded.assert_not_called()
                        self.assertEqual(stdout.getvalue(), "")
                        report = json.loads(report_path.read_bytes())
                        self.assertIs(report["passed"], False)
                        self.assertEqual(report["failure_stage"], "synthetic")
                        self.assertEqual(report["synthetic"], {})
                        self.assertNotIn("stale", report)
                        self.assertNotIn("benchmark", report)


if __name__ == "__main__":
    unittest.main()
