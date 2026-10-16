"""Edge reproduction stops on stalled children and retains failed evidence."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import edge_reproduce


class EdgeReproductionTimeouts(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self, child):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, diagnostics = io.StringIO(), io.StringIO()
            with (
                patch.object(edge_reproduce, "ROOT", root),
                patch.object(edge_reproduce, "validate_source"),
                patch.object(edge_reproduce.subprocess, "run", side_effect=child),
                patch.object(edge_reproduce.subprocess, "check_output", side_effect=child),
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(diagnostics),
            ):
                yield root, output, diagnostics

    def test_each_timeout_preserves_failure_and_stops_later_stages(self):
        for stage in range(5):
            with self.subTest(stage=stage):
                calls = []
                failure = subprocess.TimeoutExpired(
                    ["synthetic child"], 30, output=b"partial output", stderr=b"partial error"
                )

                def child(args, stage=stage, calls=calls, failure=failure, **kwargs):
                    calls.append((args, kwargs))
                    if args[1] == "clone":
                        clone = Path(args[-1])
                        clone.mkdir()
                        (clone / "partial.bin").write_bytes(b"partial evidence")
                    if len(calls) == stage + 1:
                        raise failure
                    return "a" * 40 if len(calls) == 2 else subprocess.CompletedProcess(args, 0)

                with self.fixture(child) as (root, output, diagnostics):
                    with self.assertRaises(subprocess.TimeoutExpired) as caught:
                        edge_reproduce.run(root / "wheelhouse")
                    self.assertIs(caught.exception, failure)
                    self.assertEqual(failure.output, b"partial output")
                    self.assertEqual(failure.stderr, b"partial error")
                    self.assertEqual(output.getvalue(), "")
                    self.assertEqual(len(calls), stage + 1)
                    clone = Path(calls[0][0][-1])
                    self.assertEqual((clone / "partial.bin").read_bytes(), b"partial evidence")
                    self.assertIn(str(clone.parent), diagnostics.getvalue())
                    for index, (_, kwargs) in enumerate(calls):
                        self.assertEqual(kwargs.get("timeout"), (180, 30, 600, 600, 600)[index])

    def test_real_stalled_direct_child_is_reaped_at_every_stage(self):
        invoke, popen = subprocess.run, subprocess.Popen
        for stage in range(5):
            with self.subTest(stage=stage):
                calls, children = [], []

                def spawn(*args, children=children, **kwargs):
                    process = popen(*args, **kwargs)
                    children.append(process)
                    return process

                def child(args, stage=stage, calls=calls, **kwargs):
                    calls.append(args)
                    if args[1] == "clone":
                        Path(args[-1]).mkdir()
                    if len(calls) == stage + 1:
                        invoke(
                            [sys.executable, "-c", "import time; time.sleep(1)"],
                            check=True,
                            timeout=kwargs.get("timeout", 2),
                        )
                    return "a" * 40 if len(calls) == 2 else subprocess.CompletedProcess(args, 0)

                with (
                    self.fixture(child) as (root, output, diagnostics),
                    patch.object(edge_reproduce, "GIT_CLONE_TIMEOUT_SECONDS", 0.1, create=True),
                    patch.object(edge_reproduce, "GIT_COMMAND_TIMEOUT_SECONDS", 0.1, create=True),
                    patch.object(edge_reproduce, "VERIFICATION_TIMEOUT_SECONDS", 0.1, create=True),
                    patch.object(edge_reproduce.subprocess, "Popen", side_effect=spawn),
                ):
                    with self.assertRaises(subprocess.TimeoutExpired):
                        edge_reproduce.run(root / "wheelhouse")
                    self.assertEqual(output.getvalue(), "")
                    self.assertEqual(len(calls), stage + 1)
                    clone = Path(calls[0][-1])
                    self.assertTrue(clone.is_dir())
                    self.assertIn(str(clone.parent), diagnostics.getvalue())
                    self.assertEqual(len(children), 1)
                    self.assertIsNotNone(children[0].returncode)
                    self.assertIsNotNone(children[0].poll())
