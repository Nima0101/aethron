"""A successful evaluation must include every frozen synthetic scenario."""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import temporal_evaluate as temporal


class TemporalFixtureInventory(unittest.TestCase):
    def test_incomplete_or_extra_inventory_rejects_before_execution(self):
        source = temporal.ROOT / "data/temporal"
        names = sorted(path.name for path in source.glob("*.json"))
        cases = ["absent", "empty", "extra", "directory", *names]
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                fixtures = root / "data/temporal"
                if case != "absent":
                    shutil.copytree(source, fixtures)
                    if case == "empty":
                        for path in fixtures.iterdir():
                            path.unlink()
                    elif case == "extra":
                        (fixtures / "extra.json").write_bytes(b"[]")
                    elif case == "directory":
                        (fixtures / names[0]).unlink()
                        (fixtures / names[0]).mkdir()
                    else:
                        (fixtures / case).unlink()
                output = root / "output"
                output.mkdir()
                report_path = output / "temporal-evaluation.json"
                report_path.write_bytes(b'{"passed": true, "stale": true}')
                with (
                    patch.object(temporal, "ROOT", root),
                    patch.object(temporal, "outputs", return_value=([], [])) as outputs,
                    patch.object(
                        temporal, "metrics", return_value={"recall": 1.0, "id_switches": 0}
                    ),
                    patch.object(temporal, "benchmark", return_value={"passed": True}) as bench,
                    patch.object(temporal, "recorded", return_value={}) as recorded,
                    contextlib.redirect_stdout(io.StringIO()) as stdout,
                ):
                    with self.assertRaisesRegex(ValueError, "^synthetic_fixture_inventory$"):
                        temporal.run(output)
                outputs.assert_not_called()
                bench.assert_not_called()
                recorded.assert_not_called()
                self.assertEqual(stdout.getvalue(), "")
                report = json.loads(report_path.read_bytes())
                self.assertIs(report["passed"], False)
                self.assertEqual(report["failure_stage"], "synthetic")
                self.assertEqual(report["synthetic"], {})
                self.assertNotIn("stale", report)

    def test_complete_frozen_inventory_runs_real_metrics(self):
        freeze = json.loads((temporal.ROOT / "docs/verification/data-v3-freeze.json").read_bytes())
        expected = {
            Path(name).stem for name in freeze["files"] if name.startswith("data/temporal/")
        }
        self.assertEqual(len(expected), 8)
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(temporal, "benchmark", return_value={"passed": True}),
                patch.object(temporal, "recorded") as recorded,
                contextlib.redirect_stdout(io.StringIO()),
            ):
                report = temporal.run(Path(directory), include_recorded=False)
            recorded.assert_not_called()
            self.assertIs(report["passed"], True)
            self.assertEqual(set(report["synthetic"]), expected)
            self.assertGreaterEqual(report["synthetic"]["clean"]["temporal"]["recall"], 0.9)


if __name__ == "__main__":
    unittest.main()
