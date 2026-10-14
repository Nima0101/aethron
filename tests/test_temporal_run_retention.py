"""Failed evaluation attempts survive later retries without private exception text."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import temporal_evaluate as temporal


class TemporalRunRetention(unittest.TestCase):
    def invoke(self, output, stage=None, error=None):
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(temporal, "synthetic_fixture_paths", return_value=[]))
            stack.enter_context(patch.object(temporal, "benchmark", return_value={"passed": True}))
            stack.enter_context(patch.object(temporal, "recorded", return_value={"frames": 25}))
            stdout = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            if stage == "benchmark_gate":
                stack.enter_context(
                    patch.object(
                        temporal, "benchmark", return_value={"passed": False, "peak_bytes": 42}
                    )
                )
            elif stage:
                target, name = {
                    "provenance": (temporal.platform, "python_version"),
                    "synthetic": (temporal, "synthetic_fixture_paths"),
                    "benchmark": (temporal, "benchmark"),
                    "recorded": (temporal, "recorded"),
                }[stage]
                stack.enter_context(patch.object(target, name, side_effect=error))
            if stage:
                with self.assertRaises(type(error) if error else AssertionError) as caught:
                    temporal.run(output)
                if error:
                    self.assertIs(caught.exception, error)
                self.assertEqual(stdout.getvalue(), "")
            else:
                self.assertIs(temporal.run(output)["passed"], True)

    def test_retries_keep_every_failed_stage_after_success(self):
        for stage in ("provenance", "synthetic", "benchmark", "recorded", "benchmark_gate"):
            for error_type in (RuntimeError, KeyboardInterrupt):
                with self.subTest(stage=stage, error=error_type.__name__):
                    with tempfile.TemporaryDirectory() as directory:
                        output = Path(directory)
                        retained = {}
                        for attempt in range(2):
                            error = (
                                None if stage == "benchmark_gate" else error_type("private_payload")
                            )
                            self.invoke(output, stage, error)
                            latest = (output / "temporal-evaluation.json").read_bytes()
                            report = json.loads(latest)
                            self.assertIs(report["passed"], False)
                            self.assertEqual(report["failure_stage"], stage)
                            self.assertNotIn(b"private_payload", latest)
                            current = {
                                p.name: p.read_bytes()
                                for p in output.glob("temporal-run-failure-*.json")
                            }
                            self.assertEqual(len(current), attempt + 1)
                            self.assertTrue(retained.items() <= current.items())
                            new = current.keys() - retained.keys()
                            self.assertEqual(current[new.pop()], latest)
                            retained = current
                        self.invoke(output)
                        self.assertIs(
                            json.loads((output / "temporal-evaluation.json").read_bytes())[
                                "passed"
                            ],
                            True,
                        )
                        self.assertEqual(
                            {
                                p.name: p.read_bytes()
                                for p in output.glob("temporal-run-failure-*.json")
                            },
                            retained,
                        )

    def test_success_does_not_create_failure_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            self.invoke(output)
            self.assertEqual([p.name for p in output.iterdir()], ["temporal-evaluation.json"])


if __name__ == "__main__":
    unittest.main()
