"""Real subprocess timing: failures remain failures, with bounded private-safe output."""

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aethron.evaluation.synthetic import generate

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dataset_cli_timing.py"


def harness():
    spec = importlib.util.spec_from_file_location("dataset_cli_timing", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DatasetTiming(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "dataset"
        generate(self.root)

    def test_real_comparison_has_raw_samples_and_bound_source(self):
        result = harness().run(self.root, repetitions=2)
        self.assertTrue(result["all_succeeded"])
        self.assertFalse(result["qualified"])
        self.assertEqual(len(result["samples"]), 2)
        self.assertEqual([r["status"] for r in result["samples"]], ["ok", "ok"])
        self.assertTrue(all(r["elapsed_ms"] > 0 for r in result["samples"]))
        self.assertEqual(
            result["source_sha256"]["scripts/dataset_cli_timing.py"],
            hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
        )
        pins = json.loads((self.root / "pins.json").read_bytes())
        self.assertEqual(result["manifest_sha256"], pins["manifest_sha256"])
        self.assertEqual(result["annotations_sha256"], pins["annotations_sha256"]["test"])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_repetition_bounds_and_corrupt_inputs_fail_before_launch(self):
        api = harness()
        for value in (0, 6, True, 1.5, None):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "^invalid_timing_input$"),
            ):
                api.run(self.root, repetitions=value)
        (self.root / "pins.json").write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "^invalid_timing_input$"):
            api.run(self.root, repetitions=1)

    def test_real_child_failure_timeout_bad_report_and_output_limit(self):
        api = harness()
        expected = {"version": 1}
        cases = [
            ("print('{\"version\":1}')", "ok"),
            ("import sys; print('private failure', file=sys.stderr); sys.exit(7)", "nonzero_exit"),
            ("import time; time.sleep(2)", "timeout"),
            ("print('{}')", "invalid_report"),
            ("print('{\"version\":true}')", "invalid_report"),
            ('print(\'{"version":0,"version":1}\')', "invalid_report"),
            ("print('private payload' * 10000)", "output_limit"),
        ]
        for code, status in cases:
            with self.subTest(status=status):
                result = api.sample(
                    [sys.executable, "-c", code],
                    expected,
                    timeout=0.5 if status == "timeout" else 10,
                )
                self.assertEqual(result["status"], status)
                self.assertGreater(result["elapsed_ms"], 0)
                self.assertNotIn("private", json.dumps(result))
                if status == "nonzero_exit":
                    self.assertEqual(result["returncode"], 7)

    def test_mixed_results_preserve_failure_and_do_not_retry(self):
        api = harness()
        original_sample = api.sample
        counter = 0

        def alternate(command, expected, **kwargs):
            nonlocal counter
            counter += 1
            if counter == 1:
                command = [sys.executable, "-c", "raise SystemExit(9)"]
            return original_sample(command, expected, **kwargs)

        with patch.object(api, "sample", alternate):
            result = api.run(self.root, repetitions=2)
        self.assertFalse(result["all_succeeded"])
        self.assertEqual([r["status"] for r in result["samples"]], ["nonzero_exit", "ok"])
        self.assertEqual(len(result["samples"]), 2)

    def test_source_disappearance_after_samples_preserves_observations(self):
        api = harness()
        sources = api._sources()
        with patch.object(api, "_sources", side_effect=[sources, OSError("source removed")]):
            result = api.run(self.root, repetitions=1)
        self.assertFalse(result["source_stable"])
        self.assertFalse(result["all_succeeded"])
        self.assertEqual(len(result["samples"]), 1)
        self.assertEqual(result["samples"][0]["status"], "ok")

    def test_closed_pipe_child_is_still_subject_to_deadline(self):
        api = harness()
        code = "import os,time; os.close(1); os.close(2); time.sleep(2)"
        result = api.sample([sys.executable, "-c", code], {}, timeout=0.5)
        self.assertEqual(result["status"], "timeout")

    def test_timeout_retains_stage_and_hashed_stack_without_private_text(self):
        api = harness()
        code = (
            "import sys,time,faulthandler; "
            "print('AETHRON_STAGE startup 0',file=sys.stderr,flush=True); "
            "print('AETHRON_STAGE import_start 1',file=sys.stderr,flush=True); "
            "faulthandler.dump_traceback_later(0.25); "
            "private_payload='private fixture'; time.sleep(5)"
        )
        result = api.sample([sys.executable, "-c", code], {}, timeout=3, diagnostics=True)
        self.assertEqual(result["status"], "timeout")
        self.assertEqual(
            [r["stage"] for r in result["diagnostics"]["stages"]], ["startup", "import_start"]
        )
        self.assertTrue(result["diagnostics"]["stack_line_sha256"])
        self.assertNotIn("private", json.dumps(result))
        self.assertNotIn("<string>", json.dumps(result))

    def test_diagnostic_markers_cannot_hide_bad_stderr_or_wrong_order(self):
        api = harness()
        stages = ["startup", "import_start", "import_end", "read_start", "read_end", "done"]
        for sequence, suffix, expected in (
            (stages, "", "ok"),
            (stages, "private payload", "invalid_report"),
            (list(reversed(stages)), "", "invalid_report"),
        ):
            with self.subTest(expected=expected, suffix=suffix):
                code = "import sys\n"
                for index, stage in enumerate(sequence):
                    code += f"print('AETHRON_STAGE {stage} {index}',file=sys.stderr)\n"
                if suffix:
                    code += f"print({suffix!r},file=sys.stderr)\n"
                code += "print('{}')\n"
                result = api.sample([sys.executable, "-c", code], {}, diagnostics=True)
                self.assertEqual(result["status"], expected)
                self.assertNotIn("private", json.dumps(result))

    def test_real_document_probe_runs_rejection_paths_with_stages(self):
        api = harness()
        result = api.probe_documents(repetitions=1)
        self.assertTrue(result["all_succeeded"])
        self.assertFalse(result["qualified"])
        self.assertEqual(
            [row["kind"] for row in result["samples"]], ["fifo", "symlink", "malformed"]
        )
        for row in result["samples"]:
            self.assertEqual(row["status"], "ok")
            self.assertEqual(row["diagnostics"]["stages"][-1]["stage"], "done")
        self.assertNotIn(self.temp.name, json.dumps(result))
        with self.assertRaisesRegex(ValueError, "^invalid_timing_input$"):
            api.probe_documents(repetitions=6)
