"""Exercise workspace ownership with synthetic child failures, without building packages."""

import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import edge_reproduce


class EdgeReproductionWorkspace(unittest.TestCase):
    def test_failure_retains_workspace_and_success_cleans_it(self):
        failures = (
            subprocess.CalledProcessError(7, ["synthetic-check"]),
            SystemExit(9),
            KeyboardInterrupt(),
        )
        cases = [(stage, error) for stage in range(4) for error in failures]
        cases.append((None, None))
        for failed_stage, failure in cases:
            with self.subTest(stage=failed_stage, failure=failure):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    output, diagnostics = io.StringIO(), io.StringIO()
                    calls = []
                    clones = []

                    def child(
                        args,
                        calls=calls,
                        clones=clones,
                        failed_stage=failed_stage,
                        failure=failure,
                        **kwargs,
                    ):
                        stage = len(calls)
                        calls.append(args)
                        self.assertTrue(kwargs["check"])
                        if stage == 0:
                            clone = Path(args[-1])
                            clone.mkdir()
                            clones.append(clone)
                        clone = clones[0]
                        (clone / "partial.bin").write_bytes(b"partial\x00evidence")
                        if stage == failed_stage:
                            raise failure
                        return subprocess.CompletedProcess(args, 0)

                    with (
                        patch.object(edge_reproduce, "ROOT", root),
                        patch.object(edge_reproduce.subprocess, "run", side_effect=child),
                        contextlib.redirect_stdout(output),
                        contextlib.redirect_stderr(diagnostics),
                    ):
                        if failure is None:
                            edge_reproduce.run(root / "wheelhouse")
                        else:
                            with self.assertRaises(type(failure)) as caught:
                                edge_reproduce.run(root / "wheelhouse")
                            self.assertIs(caught.exception, failure)

                    workspace = clones[0].parent
                    self.assertEqual(workspace.parent, root / "build/ecosystem-phase1")
                    self.assertTrue(workspace.name.startswith("clean-edge-"))
                    if failure is None:
                        self.assertEqual(len(calls), 4)
                        self.assertFalse(workspace.exists())
                        self.assertIn("PASS:", output.getvalue())
                        self.assertEqual(diagnostics.getvalue(), "")
                    else:
                        self.assertEqual(len(calls), failed_stage + 1)
                        self.assertTrue(workspace.is_dir(), "failed run erased its evidence")
                        self.assertEqual(
                            (clones[0] / "partial.bin").read_bytes(), b"partial\x00evidence"
                        )
                        self.assertIn(str(workspace), diagnostics.getvalue())
                        self.assertEqual(output.getvalue(), "")
